"""Écritures de MS3 dans PostgreSQL : résultats, statuts et journal des étapes.

Idempotence (NF-07, test T-08) :
    * ``resultats`` : clé primaire ``document_id`` + ``ON CONFLICT DO UPDATE``
      -> un événement ``ocr.completed`` reçu deux fois ne crée qu'un résultat ;
    * ``journal_etapes`` : clé primaire ``event_id`` + ``ON CONFLICT DO NOTHING``
      -> un événement relivré n'est journalisé qu'une fois ;
    * un statut terminal (``COMPLETED``/``FAILED``) n'est jamais rétrogradé.
"""

from __future__ import annotations

import json

from sqlalchemy import Engine, text

from docflow.commun.contrats import Evenement, TypeEvenement
from docflow.extraction.extracteur import ResultatExtraction

# Détails conservés dans le journal : jamais le texte OCR ni les valeurs du ticket.
CHAMPS_JOURNAL = {
    TypeEvenement.DOCUMENT_RECU: ("format_source", "taille_octets"),
    TypeEvenement.ETAPE_DEMARREE: ("etape",),
    TypeEvenement.PRETRAITEMENT_TERMINE: ("nb_pages", "format_source", "angles"),
    TypeEvenement.OCR_TERMINE: ("pages_vides", "moteur"),
    TypeEvenement.EXTRACTION_TERMINEE: ("methode", "champs_manquants", "champs_incertains",
                                        "version_modele"),
    TypeEvenement.ECHEC: ("etape", "cause", "definitif", "tentatives"),
}

SQL_RESULTAT = text("""
    INSERT INTO resultats (document_id, entity, date, total_amount, currency, confidence,
                           methode, champs_manquants, champs_incertains, version_modele)
    VALUES (:document_id, :entity, :date, :total_amount, :currency, CAST(:confidence AS jsonb),
            CAST(:methode AS jsonb), :champs_manquants, :champs_incertains, :version_modele)
    ON CONFLICT (document_id) DO UPDATE SET
        entity = EXCLUDED.entity, date = EXCLUDED.date, total_amount = EXCLUDED.total_amount,
        currency = EXCLUDED.currency, confidence = EXCLUDED.confidence, methode = EXCLUDED.methode,
        champs_manquants = EXCLUDED.champs_manquants, champs_incertains = EXCLUDED.champs_incertains,
        version_modele = EXCLUDED.version_modele, updated_at = now()
""")

SQL_STATUT = text("""
    UPDATE documents SET status = CAST(:statut AS statut_document), erreur = :erreur, updated_at = now()
    WHERE document_id = :document_id AND status NOT IN ('COMPLETED', 'FAILED')
""")

SQL_JOURNAL = text("""
    INSERT INTO journal_etapes (event_id, document_id, event_type, service, emis_le,
                                duree_ms, attente_ms, details)
    VALUES (:event_id, :document_id, :event_type, :service, :emis_le,
            :duree_ms, :attente_ms, CAST(:details AS jsonb))
    ON CONFLICT (event_id) DO NOTHING
""")


class DepotMS3:
    """Accès base de MS3 (compte ``docflow_ms3``)."""

    def __init__(self, moteur: Engine) -> None:
        self.moteur = moteur

    def enregistrer_resultat(self, document_id: str, r: ResultatExtraction) -> None:
        """Écrit (ou réécrit) le résultat et passe le document à ``COMPLETED``,
        dans une même transaction."""
        with self.moteur.begin() as cx:
            cx.execute(SQL_RESULTAT, {
                "document_id": document_id,
                "entity": r.entity,
                "date": r.date,
                "total_amount": r.total_amount,
                "currency": r.currency,
                "confidence": json.dumps(r.confidence),
                "methode": json.dumps(r.methode),
                "champs_manquants": r.champs_manquants,
                "champs_incertains": r.champs_incertains,
                "version_modele": r.version_modele,
            })
            cx.execute(SQL_STATUT, {"document_id": document_id, "statut": "COMPLETED",
                                    "erreur": None})

    def journaliser(self, e: Evenement) -> bool:
        """Enregistre un événement et met à jour le statut qui en découle.

        Retourne ``False`` si l'événement était déjà connu (relivraison).
        """
        details = {k: e.payload[k] for k in CHAMPS_JOURNAL.get(e.event_type, ()) if k in e.payload}
        with self.moteur.begin() as cx:
            nouveau = cx.execute(SQL_JOURNAL, {
                "event_id": e.event_id,
                "document_id": e.document_id,
                "event_type": str(e.event_type),
                "service": e.service,
                "emis_le": e.created_at,
                "duree_ms": e.payload.get("duree_ms"),
                "attente_ms": e.payload.get("attente_ms"),
                "details": json.dumps(details),
            }).rowcount == 1
            if e.event_type == TypeEvenement.ETAPE_DEMARREE:
                cx.execute(SQL_STATUT, {"document_id": e.document_id, "statut": "PROCESSING",
                                        "erreur": None})
            elif e.event_type == TypeEvenement.ECHEC:
                cause = f"[{e.payload.get('etape')}] {e.payload.get('cause')}"
                cx.execute(SQL_STATUT, {"document_id": e.document_id, "statut": "FAILED",
                                        "erreur": cause[:500]})
        return nouveau
