"""MS1 — service de prétraitement documentaire.

Consomme ``document.received`` et publie ``preprocessing.completed``.

    python -m docflow.pretraitement.service

Variables d'environnement : ``RABBITMQ_URL``, ``DOCFLOW_STORAGE``.
"""

from __future__ import annotations

from docflow.commun.config import dossier_stockage
from docflow.commun.contrats import (
    DocumentRecu,
    EtapeDemarree,
    Evenement,
    PretraitementTermine,
    TypeEvenement,
)
from docflow.commun.journal import configurer_journaux, contexte
from docflow.commun.messagerie import ErreurDefinitive, Worker, attente_depuis
from docflow.commun.stockage import ReferenceInvalide, vers_chemin, vers_reference
from docflow.pretraitement.traitement import ErreurDocument, pretraiter

SERVICE = "ms1-pretraitement"
log = configurer_journaux(SERVICE)


def traiter(evenement: Evenement, publier) -> None:
    """Prépare les pages d'un document déposé.

    Exemple : ``storage://originaux/DOC-0002.pdf``
              -> ``storage://pretraite/DOC-0002/page_001.png``
    """
    publier(evenement.suite(TypeEvenement.ETAPE_DEMARREE, SERVICE,
                            EtapeDemarree(etape="pretraitement", attente_ms=attente_depuis(evenement))))
    recu: DocumentRecu = evenement.charge(DocumentRecu)
    racine = dossier_stockage()
    try:
        source = vers_chemin(recu.original_ref, racine)
        contenu = source.read_bytes()
    except (ReferenceInvalide, FileNotFoundError) as exc:
        raise ErreurDefinitive(f"Document original introuvable ({type(exc).__name__})") from exc

    sortie = racine / "pretraite" / evenement.document_id
    try:
        resultat = pretraiter(contenu, sortie)
    except ErreurDocument as exc:
        raise ErreurDefinitive(str(exc)) from exc

    log.info(contexte(evenement.document_id, etape="pretraitement", pages=resultat.nb_pages,
                      format=resultat.format_source, duree_ms=resultat.duree_ms,
                      angles=",".join(f"{a:g}" for a in resultat.angles)))
    publier(evenement.suite(
        TypeEvenement.PRETRAITEMENT_TERMINE, SERVICE,
        PretraitementTermine(
            pages_refs=[vers_reference(p, racine) for p in resultat.pages],
            nb_pages=resultat.nb_pages,
            format_source=resultat.format_source,
            duree_ms=resultat.duree_ms,
            angles=resultat.angles,
        ),
    ))


def main() -> None:
    Worker(SERVICE, "pretraitement", {"docflow.ms1.pretraitement": traiter}, log).demarrer()


if __name__ == "__main__":
    main()
