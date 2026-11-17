"""Contrats des messages échangés sur RabbitMQ (version ``v1``).

Chaque message est une **enveloppe** commune (identifiants, type, date,
service émetteur) contenant une **charge utile** propre au type d'événement.
Les fichiers et images ne voyagent jamais : seulement leurs références
``storage://`` — sauf le texte OCR, transmis dans ``ocr.completed`` car MS3
(sur Fedora) n'a pas accès au stockage du Mac (voir ``docs/contrats.md``).

Exemple d'enveloppe :
    {
      "event_id": "0b6f…", "event_type": "ocr.completed", "version": "v1",
      "document_id": "DOC-3F2A9C01B7D4", "correlation_id": "RUN-91AC…",
      "created_at": "2026-11-16T15:00:00Z", "service": "ms2-ocr",
      "payload": {"pages": [...], "duree_ms": 812, ...}
    }
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

VERSION_CONTRAT = "v1"


class TypeEvenement(StrEnum):
    """Noms d'événements = clés de routage RabbitMQ."""

    DOCUMENT_RECU = "document.received"
    ETAPE_DEMARREE = "step.started"
    PRETRAITEMENT_TERMINE = "preprocessing.completed"
    OCR_TERMINE = "ocr.completed"
    EXTRACTION_TERMINEE = "extraction.completed"
    ECHEC = "processing.failed"


Etape = Literal["pretraitement", "ocr", "extraction"]


def nouvel_identifiant(prefixe: str) -> str:
    """Identifiant lisible et unique, ex. ``DOC-3F2A9C01B7D4``."""
    return f"{prefixe}-{uuid.uuid4().hex[:12].upper()}"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ charges utiles
class DocumentRecu(_Strict):
    original_ref: str
    format_source: Literal["pdf", "png", "jpeg"]
    taille_octets: int = Field(gt=0)


class EtapeDemarree(_Strict):
    etape: Etape
    attente_ms: int | None = None  # temps passé dans la file avant traitement


class PretraitementTermine(_Strict):
    pages_refs: list[str] = Field(min_length=1)
    nb_pages: int
    format_source: str
    duree_ms: int
    angles: list[float] = []


class LigneMessage(_Strict):
    texte: str
    y_rel: float
    confiance: float


class PageMessage(_Strict):
    numero: int
    lignes: list[LigneMessage]
    nb_mots: int
    confiance_moyenne: float


class OcrTermine(_Strict):
    pages: list[PageMessage]
    pages_vides: list[int] = []
    duree_ms: int
    moteur: str


class ExtractionTerminee(_Strict):
    entity: str
    date: str | None
    total_amount: str | None  # chaîne pour ne pas perdre la précision décimale
    currency: str | None
    champs_manquants: list[str]
    champs_incertains: list[str]
    methode: dict[str, str]
    confidence: dict[str, float]
    version_modele: str
    duree_ms: int


class Echec(_Strict):
    etape: Etape | Literal["api"]
    cause: str  # message compréhensible, sans contenu du ticket
    definitif: bool  # True : inutile de réessayer (fichier corrompu…)
    tentatives: int = 1


# ------------------------------------------------------------------ enveloppe
class Evenement(_Strict):
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    event_type: TypeEvenement
    version: Literal["v1"] = VERSION_CONTRAT
    document_id: str
    correlation_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    service: str
    payload: dict[str, Any]

    @classmethod
    def creer(cls, type_: TypeEvenement, document_id: str, correlation_id: str,
              service: str, charge: BaseModel) -> Evenement:
        """Construit un événement à partir d'une charge utile typée.

        Exemple :
            >>> e = Evenement.creer(TypeEvenement.ETAPE_DEMARREE, "DOC-1", "RUN-1", "ms1",
            ...                     EtapeDemarree(etape="pretraitement", attente_ms=12))
            >>> e.payload
            {'etape': 'pretraitement', 'attente_ms': 12}
        """
        return cls(event_type=type_, document_id=document_id, correlation_id=correlation_id,
                   service=service, payload=charge.model_dump(mode="json"))

    def suite(self, type_: TypeEvenement, service: str, charge: BaseModel) -> Evenement:
        """Événement suivant du même document (identifiants conservés)."""
        return Evenement.creer(type_, self.document_id, self.correlation_id, service, charge)

    def charge(self, modele: type[BaseModel]) -> Any:
        """Valide et retourne la charge utile selon ``modele``."""
        return modele.model_validate(self.payload)

    def en_octets(self) -> bytes:
        return self.model_dump_json().encode("utf-8")

    @classmethod
    def depuis_octets(cls, donnees: bytes) -> Evenement:
        return cls.model_validate_json(donnees)
