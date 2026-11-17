"""Accès base de l'API (compte ``docflow_api`` : lecture + création de documents).

L'API (Mac) lit les résultats directement dans PostgreSQL (Fedora) via un
compte dédié aux droits limités (décision Q-03, cahier des charges §6.2).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, text


class DepotAPI:
    def __init__(self, moteur: Engine) -> None:
        self.moteur = moteur

    def ping(self) -> None:
        with self.moteur.connect() as cx:
            cx.execute(text("SELECT 1"))

    def creer_document(self, document_id: str, correlation_id: str, format_source: str,
                       taille_octets: int, original_ref: str) -> None:
        with self.moteur.begin() as cx:
            cx.execute(text("""
                INSERT INTO documents (document_id, correlation_id, format_source, taille_octets,
                                       original_ref, status)
                VALUES (:d, :c, :f, :t, :r, 'PENDING')
            """), {"d": document_id, "c": correlation_id, "f": format_source, "t": taille_octets,
                   "r": original_ref})

    def marquer_echec(self, document_id: str, cause: str) -> None:
        with self.moteur.begin() as cx:
            cx.execute(text("""
                UPDATE documents SET status = 'FAILED', erreur = :e, updated_at = now()
                WHERE document_id = :d
            """), {"d": document_id, "e": cause})

    def lire(self, document_id: str) -> dict[str, Any] | None:
        """Document + résultat + étapes, ou ``None`` s'il n'existe pas."""
        with self.moteur.connect() as cx:
            doc = cx.execute(text("""
                SELECT d.document_id, d.correlation_id, d.status::text AS status, d.erreur,
                       d.format_source, d.taille_octets, d.created_at, d.updated_at,
                       r.entity, r.date, r.total_amount, r.currency, r.confidence, r.methode,
                       r.champs_manquants, r.champs_incertains, r.version_modele
                FROM documents d LEFT JOIN resultats r USING (document_id)
                WHERE d.document_id = :d
            """), {"d": document_id}).mappings().first()
            if doc is None:
                return None
            etapes = cx.execute(text("""
                SELECT event_type, service, emis_le, duree_ms, attente_ms, details
                FROM journal_etapes WHERE document_id = :d ORDER BY emis_le
            """), {"d": document_id}).mappings().all()
        return {"document": dict(doc), "etapes": [dict(e) for e in etapes]}

    def lister(self, limite: int) -> list[dict[str, Any]]:
        with self.moteur.connect() as cx:
            lignes = cx.execute(text("""
                SELECT d.document_id, d.status::text AS status, d.created_at, d.updated_at,
                       r.entity, r.date, r.total_amount, r.currency
                FROM documents d LEFT JOIN resultats r USING (document_id)
                ORDER BY d.created_at DESC LIMIT :n
            """), {"n": limite}).mappings().all()
        return [dict(l) for l in lignes]  # noqa: E741
