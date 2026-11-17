"""MS2 — service OCR.

Consomme ``preprocessing.completed`` et publie ``ocr.completed`` avec les
lignes reconnues (le texte voyage dans le message : MS3, sur Fedora, n'a pas
accès au stockage du Mac).

    python -m docflow.ocr.service

Variables d'environnement : ``RABBITMQ_URL``, ``DOCFLOW_STORAGE``,
``OCR_LANGUE`` (défaut ``fra``), ``OCR_CONFIG``.
"""

from __future__ import annotations

import time

from docflow.commun.config import dossier_stockage
from docflow.commun.contrats import (
    EtapeDemarree,
    Evenement,
    LigneMessage,
    OcrTermine,
    PageMessage,
    PretraitementTermine,
    TypeEvenement,
)
from docflow.commun.journal import configurer_journaux, contexte
from docflow.commun.messagerie import ErreurDefinitive, Worker, attente_depuis
from docflow.commun.stockage import ReferenceInvalide, vers_chemin
from docflow.ocr.moteur import lire_document, version_tesseract

SERVICE = "ms2-ocr"
log = configurer_journaux(SERVICE)


def traiter(evenement: Evenement, publier) -> None:
    """Lit le texte de toutes les pages préparées d'un document."""
    publier(evenement.suite(TypeEvenement.ETAPE_DEMARREE, SERVICE,
                            EtapeDemarree(etape="ocr", attente_ms=attente_depuis(evenement))))
    pre: PretraitementTermine = evenement.charge(PretraitementTermine)
    racine = dossier_stockage()
    try:
        chemins = [vers_chemin(ref, racine) for ref in pre.pages_refs]
    except ReferenceInvalide as exc:
        raise ErreurDefinitive("Référence d'image invalide") from exc
    if not all(c.exists() for c in chemins):
        raise ErreurDefinitive("Image préparée introuvable dans le stockage")

    debut = time.perf_counter()
    pages = lire_document(chemins)
    duree = round((time.perf_counter() - debut) * 1000)
    vides = [p.numero for p in pages if not p.texte]
    log.info(contexte(evenement.document_id, etape="ocr", pages=len(pages), duree_ms=duree,
                      mots=sum(p.nb_mots for p in pages), pages_vides=vides or "aucune"))

    publier(evenement.suite(
        TypeEvenement.OCR_TERMINE, SERVICE,
        OcrTermine(
            pages=[
                PageMessage(
                    numero=p.numero,
                    lignes=[LigneMessage(texte=l.texte, y_rel=l.y_rel, confiance=l.confiance)
                            for l in p.lignes],  # noqa: E741
                    nb_mots=p.nb_mots,
                    confiance_moyenne=p.confiance_moyenne,
                )
                for p in pages
            ],
            pages_vides=vides,
            duree_ms=duree,
            moteur=f"tesseract-{version_tesseract()}",
        ),
    ))


def main() -> None:
    Worker(SERVICE, "ocr", {"docflow.ms2.ocr": traiter}, log).demarrer()


if __name__ == "__main__":
    main()
