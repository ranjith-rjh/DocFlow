"""Tests des contrats de messages et de la logique de tentatives du worker."""

import logging
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from docflow.commun import messagerie
from docflow.commun.contrats import (
    DocumentRecu,
    Echec,
    Evenement,
    OcrTermine,
    TypeEvenement,
    nouvel_identifiant,
)
from docflow.commun.messagerie import ENTETE_TENTATIVE, ErreurDefinitive, Worker


def evenement_recu() -> Evenement:
    return Evenement.creer(TypeEvenement.DOCUMENT_RECU, "DOC-1", "RUN-1", "api",
                           DocumentRecu(original_ref="storage://originaux/DOC-1.pdf",
                                        format_source="pdf", taille_octets=10))


def test_aller_retour_json_conserve_tout():
    e = evenement_recu()
    relu = Evenement.depuis_octets(e.en_octets())
    assert relu == e
    assert relu.charge(DocumentRecu).format_source == "pdf"


def test_suite_conserve_les_identifiants():
    e = evenement_recu()
    s = e.suite(TypeEvenement.ECHEC, "ms1", Echec(etape="pretraitement", cause="x", definitif=True))
    assert (s.document_id, s.correlation_id) == (e.document_id, e.correlation_id)
    assert s.event_id != e.event_id


def test_contrat_strict_refuse_champs_inconnus_et_mauvaise_version():
    brut = evenement_recu().model_dump(mode="json")
    with pytest.raises(ValidationError):
        Evenement.model_validate({**brut, "inattendu": 1})
    with pytest.raises(ValidationError):
        Evenement.model_validate({**brut, "version": "v2"})
    with pytest.raises(ValidationError):
        DocumentRecu(original_ref="storage://x", format_source="gif", taille_octets=1)


def test_charge_ocr_invalide_refusee():
    e = evenement_recu()
    with pytest.raises(ValidationError):
        e.charge(OcrTermine)


def test_identifiants_lisibles_et_uniques():
    a, b = nouvel_identifiant("DOC"), nouvel_identifiant("DOC")
    assert a.startswith("DOC-") and len(a) == 16 and a != b


# ------------------------------------------------------------------ worker
class FauxCanal:
    """Canal RabbitMQ minimal qui enregistre acquittements et publications."""

    def __init__(self):
        self.acks, self.nacks, self.publies = [], [], []
        self.connection = SimpleNamespace(sleep=lambda s: None)

    def basic_ack(self, tag):
        self.acks.append(tag)

    def basic_nack(self, tag, requeue):
        self.nacks.append((tag, requeue))


@pytest.fixture
def canal(monkeypatch):
    c = FauxCanal()

    def faux_publier(canal, evenement, file_directe=None, entetes=None):
        c.publies.append((evenement, file_directe, entetes))

    monkeypatch.setattr(messagerie, "publier", faux_publier)
    return c


def lancer(canal, traiter, tentative=1, corps=None, file="f"):
    worker = Worker("ms-test", "ocr", {file: traiter}, logging.getLogger("test"),
                    files_sans_echec=frozenset({"journal"}))
    proprietes = SimpleNamespace(headers={ENTETE_TENTATIVE: tentative})
    worker._traiter_message(canal, SimpleNamespace(delivery_tag=7), proprietes,
                            corps or evenement_recu().en_octets(), file, traiter)


def test_succes_acquitte_apres_traitement(canal):
    lancer(canal, lambda e, publier: None)
    assert canal.acks == [7] and canal.nacks == []


def test_erreur_temporaire_republie_avec_tentative_suivante(canal):
    def echoue(e, publier):
        raise ConnectionError("base injoignable")

    lancer(canal, echoue, tentative=1)
    evenement, file, entetes = canal.publies[0]
    assert file == "f" and entetes == {ENTETE_TENTATIVE: 2}
    assert canal.acks == [7]


def test_abandon_apres_max_tentatives_vers_file_erreur(canal):
    def echoue(e, publier):
        raise ConnectionError("toujours en panne")

    lancer(canal, echoue, tentative=messagerie.MAX_TENTATIVES)
    echec = canal.publies[0][0]
    assert echec.event_type == TypeEvenement.ECHEC
    assert echec.payload["definitif"] is False
    assert canal.nacks == [(7, False)]  # -> dead-letter exchange


def test_erreur_definitive_sans_nouvelle_tentative(canal):
    def corrompu(e, publier):
        raise ErreurDefinitive("PDF illisible ou corrompu")

    lancer(canal, corrompu)
    assert len(canal.publies) == 1
    assert canal.publies[0][0].payload == {"etape": "ocr", "cause": "PDF illisible ou corrompu",
                                           "definitif": True, "tentatives": 1}
    assert canal.acks == [7]


def test_message_illisible_part_en_file_erreur(canal):
    lancer(canal, lambda e, p: None, corps=b"{pas du json")
    assert canal.nacks == [(7, False)] and canal.publies == []


def test_echec_du_journal_ne_fait_pas_echouer_le_document(canal):
    def echoue(e, publier):
        raise ErreurDefinitive("document inconnu")

    lancer(canal, echoue, file="journal")
    assert canal.publies == [] and canal.acks == [7]
