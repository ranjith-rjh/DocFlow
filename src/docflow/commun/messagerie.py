"""Socle RabbitMQ commun à l'API et aux trois workers.

Topologie (déclarée de façon idempotente par chaque composant au démarrage) :

    exchange topic « docflow.events »
        document.received        -> docflow.ms1.pretraitement   (MS1)
        preprocessing.completed  -> docflow.ms2.ocr             (MS2)
        ocr.completed            -> docflow.ms3.extraction      (MS3)
        #  (tous les événements)  -> docflow.ms3.journal         (MS3 : statuts, durées)
    exchange fanout « docflow.dlx » -> docflow.erreurs  (messages abandonnés)

Garanties de fiabilité (cahier des charges §6.3) :
    * files durables et messages persistants (survivent à un redémarrage) ;
    * confirmations de publication (le broker accuse réception) ;
    * acquittement **après** succès du traitement ;
    * ``prefetch=1`` : un worker ne réserve qu'un message à la fois ;
    * tentatives limitées (``MAX_TENTATIVES``) puis file d'erreur ;
    * erreur « définitive » (fichier corrompu) : pas de nouvelle tentative.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import AMQPConnectionError, AMQPError
from pydantic import ValidationError

from docflow.commun.config import env_int, url_rabbitmq
from docflow.commun.contrats import Echec, Evenement, TypeEvenement
from docflow.commun.journal import contexte

EXCHANGE = "docflow.events"
DLX = "docflow.dlx"
FILE_ERREURS = "docflow.erreurs"
FILES: dict[str, list[str]] = {
    "docflow.ms1.pretraitement": [TypeEvenement.DOCUMENT_RECU],
    "docflow.ms2.ocr": [TypeEvenement.PRETRAITEMENT_TERMINE],
    "docflow.ms3.extraction": [TypeEvenement.OCR_TERMINE],
    "docflow.ms3.journal": ["#"],
}
MAX_TENTATIVES = env_int("MAX_TENTATIVES", 3)
ENTETE_TENTATIVE = "x-docflow-tentative"


class ErreurDefinitive(Exception):
    """Erreur qui ne disparaîtra pas en réessayant (document illisible…)."""


def connecter(url: str | None = None, log: logging.Logger | None = None,
              essais: int | None = None) -> pika.BlockingConnection:
    """Ouvre une connexion en réessayant avec un délai croissant (max 30 s).

    Permet de démarrer un worker avant RabbitMQ, ou de survivre à un
    redémarrage du broker. ``essais=None`` : réessaie indéfiniment.
    """
    parametres = pika.URLParameters(url or url_rabbitmq())
    parametres.heartbeat = 120
    parametres.blocked_connection_timeout = 60
    delai, essai = 1.0, 0
    while True:
        essai += 1
        try:
            return pika.BlockingConnection(parametres)
        except AMQPConnectionError:
            if essais is not None and essai >= essais:
                raise
            if log:
                log.warning(contexte(None, evenement="rabbitmq_indisponible", nouvel_essai_s=delai))
            time.sleep(delai)
            delai = min(delai * 2, 30.0)


def declarer_topologie(canal: BlockingChannel) -> None:
    """Déclare exchanges, files et liaisons (sans effet si elles existent déjà)."""
    canal.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
    canal.exchange_declare(DLX, exchange_type="fanout", durable=True)
    canal.queue_declare(FILE_ERREURS, durable=True)
    canal.queue_bind(FILE_ERREURS, DLX)
    for file, cles in FILES.items():
        canal.queue_declare(file, durable=True, arguments={"x-dead-letter-exchange": DLX})
        for cle in cles:
            canal.queue_bind(file, EXCHANGE, routing_key=str(cle))


def publier(canal: BlockingChannel, evenement: Evenement, file_directe: str | None = None,
            entetes: dict | None = None) -> None:
    """Publie un événement persistant ; lève une exception si le broker le refuse.

    ``file_directe`` : republie directement dans une file (nouvelle tentative)
    au lieu de passer par l'exchange.
    """
    proprietes = pika.BasicProperties(
        delivery_mode=pika.DeliveryMode.Persistent,
        content_type="application/json",
        message_id=evenement.event_id,
        correlation_id=evenement.correlation_id,
        type=str(evenement.event_type),
        headers=entetes or {},
    )
    if file_directe:
        canal.basic_publish("", file_directe, evenement.en_octets(), proprietes, mandatory=True)
    else:
        canal.basic_publish(EXCHANGE, str(evenement.event_type), evenement.en_octets(),
                            proprietes, mandatory=True)


def publier_une_fois(evenement: Evenement) -> None:
    """Connexion courte pour publier un seul événement (utilisé par l'API)."""
    connexion = connecter(essais=2)
    try:
        canal = connexion.channel()
        canal.confirm_delivery()
        declarer_topologie(canal)
        publier(canal, evenement)
    finally:
        connexion.close()


def attente_depuis(evenement: Evenement) -> int:
    """Millisecondes écoulées depuis l'émission (≈ temps passé en file)."""
    return max(0, round((datetime.now(UTC) - evenement.created_at).total_seconds() * 1000))


Traitement = Callable[[Evenement, Callable[[Evenement], None]], None]


class Worker:
    """Boucle de consommation commune à MS1, MS2 et MS3.

    ``abonnements`` associe une file à une fonction ``traiter(evenement, publier)``.
    La fonction lève :class:`ErreurDefinitive` pour un échec sans espoir, ou
    toute autre exception pour un échec temporaire (nouvelle tentative).
    """

    def __init__(self, service: str, etape: str, abonnements: dict[str, Traitement],
                 log: logging.Logger, files_sans_echec: frozenset[str] = frozenset()) -> None:
        self.service = service
        self.etape = etape
        self.abonnements = abonnements
        self.log = log
        # Files dont l'échec ne doit pas faire échouer le document (ex. journal :
        # un statut non enregistré ne signifie pas que le traitement a échoué).
        self.files_sans_echec = files_sans_echec

    # -------------------------------------------------------------- boucle
    def demarrer(self) -> None:
        """Consomme indéfiniment ; se reconnecte si RabbitMQ disparaît."""
        while True:
            try:
                connexion = connecter(log=self.log)
                canal = connexion.channel()
                canal.confirm_delivery()
                declarer_topologie(canal)
                canal.basic_qos(prefetch_count=1)
                for file, traiter in self.abonnements.items():
                    canal.basic_consume(file, self._rappel(file, traiter))
                self.log.info(contexte(None, evenement="pret", files=",".join(self.abonnements)))
                canal.start_consuming()
            except AMQPError as exc:
                self.log.warning(contexte(None, evenement="connexion_perdue", erreur=type(exc).__name__))
                time.sleep(2)
            except KeyboardInterrupt:
                self.log.info(contexte(None, evenement="arret"))
                return

    def _rappel(self, file: str, traiter: Traitement):
        def rappel(canal: BlockingChannel, methode, proprietes, corps: bytes) -> None:
            self._traiter_message(canal, methode, proprietes, corps, file, traiter)

        return rappel

    # -------------------------------------------------------------- un message
    def _traiter_message(self, canal, methode, proprietes, corps, file, traiter) -> None:
        try:
            evenement = Evenement.depuis_octets(corps)
        except ValidationError as exc:
            # Message invalide : inutile de réessayer, direction file d'erreur.
            self.log.error(contexte(None, evenement="message_invalide", file=file,
                                    erreurs=exc.error_count()))
            canal.basic_nack(methode.delivery_tag, requeue=False)
            return

        tentative = int((proprietes.headers or {}).get(ENTETE_TENTATIVE, 1))
        try:
            traiter(evenement, lambda e: publier(canal, e))
        except ErreurDefinitive as exc:
            self.log.warning(contexte(evenement.document_id, evenement="echec_definitif",
                                      etape=self.etape, cause=str(exc)))
            if file not in self.files_sans_echec:
                self._signaler_echec(canal, evenement, str(exc), definitif=True, tentatives=tentative)
            canal.basic_ack(methode.delivery_tag)
        except Exception as exc:  # erreur temporaire : base, réseau, bug ponctuel…
            cause = f"{type(exc).__name__}: {exc}"[:300]
            if tentative < MAX_TENTATIVES:
                self.log.warning(contexte(evenement.document_id, evenement="nouvelle_tentative",
                                          etape=self.etape, tentative=tentative + 1, cause=cause))
                canal.connection.sleep(min(2 ** tentative, 10))
                publier(canal, evenement, file_directe=file,
                        entetes={ENTETE_TENTATIVE: tentative + 1})
                canal.basic_ack(methode.delivery_tag)
            else:
                self.log.error(contexte(evenement.document_id, evenement="abandon",
                                        etape=self.etape, tentatives=tentative, cause=cause))
                if file not in self.files_sans_echec:
                    self._signaler_echec(canal, evenement, cause, definitif=False, tentatives=tentative)
                canal.basic_nack(methode.delivery_tag, requeue=False)  # -> docflow.erreurs
        else:
            canal.basic_ack(methode.delivery_tag)

    def _signaler_echec(self, canal, evenement: Evenement, cause: str, definitif: bool,
                        tentatives: int) -> None:
        if evenement.event_type == TypeEvenement.ECHEC:
            return  # ne jamais boucler sur un échec d'échec
        echec = evenement.suite(TypeEvenement.ECHEC, self.service,
                                Echec(etape=self.etape, cause=cause, definitif=definitif,
                                      tentatives=tentatives))
        publier(canal, echec)
