"""MS3 — service d'extraction métier et d'insertion (nœud B, Fedora).

Deux abonnements dans un même processus :
    * ``docflow.ms3.extraction`` (``ocr.completed``) : extraire les trois
      champs, les enregistrer, publier ``extraction.completed`` ;
    * ``docflow.ms3.journal`` (tous les événements) : tenir à jour les statuts
      et les durées de chaque étape (traçabilité NF-06).

Ainsi seuls l'API (création, lecture) et MS3 (écriture) accèdent à
PostgreSQL ; MS1 et MS2 n'ont aucun accès à la base (décision Q-03).

    python -m docflow.extraction.service

Variables d'environnement : ``RABBITMQ_URL``, ``DATABASE_URL``,
``EXTRACTION_MODE`` (``modele`` ou ``regles``), ``MODELE_CHEMIN``.
"""

from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from docflow.commun.base import moteur
from docflow.commun.config import env
from docflow.commun.contrats import (
    EtapeDemarree,
    Evenement,
    ExtractionTerminee,
    OcrTermine,
    TypeEvenement,
)
from docflow.commun.journal import configurer_journaux, contexte
from docflow.commun.messagerie import ErreurDefinitive, Worker, attente_depuis
from docflow.extraction.depot import DepotMS3
from docflow.extraction.extracteur import Selecteur, extraire

SERVICE = "ms3-extraction"
log = configurer_journaux(SERVICE)


def charger_selecteur() -> Selecteur | None:
    """Charge le modèle entraîné, ou ``None`` pour la baseline par règles."""
    mode = env("EXTRACTION_MODE", "modele")
    chemin = Path(env("MODELE_CHEMIN", "models/docflow-extraction.joblib"))
    if mode != "modele":
        log.info(contexte(None, evenement="mode_extraction", mode="regles"))
        return None
    if not chemin.exists():
        log.warning(contexte(None, evenement="modele_absent", chemin=chemin, repli="regles"))
        return None
    from docflow.extraction.modele import ModeleExtraction

    selecteur = ModeleExtraction.charger(chemin)
    log.info(contexte(None, evenement="modele_charge", version=selecteur.version))
    return selecteur


class ServiceMS3:
    def __init__(self, depot: DepotMS3, selecteur: Selecteur | None) -> None:
        self.depot = depot
        self.selecteur = selecteur

    def extraire(self, evenement: Evenement, publier) -> None:
        """Texte OCR -> résultat structuré en base -> ``extraction.completed``."""
        publier(evenement.suite(TypeEvenement.ETAPE_DEMARREE, SERVICE,
                                EtapeDemarree(etape="extraction", attente_ms=attente_depuis(evenement))))
        ocr: OcrTermine = evenement.charge(OcrTermine)
        debut = time.perf_counter()
        resultat = extraire([p.model_dump() for p in ocr.pages], self.selecteur)
        try:
            self.depot.enregistrer_resultat(evenement.document_id, resultat)
        except IntegrityError as exc:
            raise ErreurDefinitive("Document inconnu en base ou valeur refusée") from exc
        duree = round((time.perf_counter() - debut) * 1000)
        log.info(contexte(evenement.document_id, etape="extraction", duree_ms=duree,
                          manquants=",".join(resultat.champs_manquants) or "aucun",
                          methode=",".join(f"{k}:{v}" for k, v in resultat.methode.items())))
        d = resultat.en_dict()
        publier(evenement.suite(TypeEvenement.EXTRACTION_TERMINEE, SERVICE, ExtractionTerminee(
            entity=d["entity"], date=d["date"], total_amount=d["total_amount"],
            currency=d["currency"], champs_manquants=d["champs_manquants"],
            champs_incertains=d["champs_incertains"], methode=d["methode"],
            confidence=d["confidence"], version_modele=d["version_modele"], duree_ms=duree,
        )))

    def journaliser(self, evenement: Evenement, _publier) -> None:
        """Enregistre l'événement et le statut correspondant."""
        try:
            nouveau = self.depot.journaliser(evenement)
        except IntegrityError as exc:
            raise ErreurDefinitive("Événement d'un document inconnu en base") from exc
        if not nouveau:
            log.info(contexte(evenement.document_id, evenement="doublon_ignore",
                              type=evenement.event_type))


def main() -> None:
    service = ServiceMS3(DepotMS3(moteur()), charger_selecteur())
    Worker(
        SERVICE, "extraction",
        {"docflow.ms3.extraction": service.extraire, "docflow.ms3.journal": service.journaliser},
        log,
        files_sans_echec=frozenset({"docflow.ms3.journal"}),
    ).demarrer()


if __name__ == "__main__":
    main()
