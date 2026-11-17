"""Orchestration de l'extraction : texte OCR -> entité, date, total.

Deux modes, choisis par configuration (``EXTRACTION_MODE``) :
    * ``regles`` : baseline par mots-clés (``regles.py``) ;
    * ``modele`` : approche hybride entraînée (``modele.py``) — génération de
      candidats par règles, **sélection apprise**, repli sur les règles si le
      modèle n'a aucun candidat.

Pour chaque champ, le résultat indique la méthode réellement utilisée
(exigence scientifique du §8.4) et une confiance documentée.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol

from docflow.extraction import regles
from docflow.extraction.candidats import (
    CandidatDate,
    CandidatMontant,
    Ligne,
    aplatir,
    candidats_dates,
    candidats_montants,
)
from docflow.extraction.normalisation import INCONNUE

SEUIL_INCERTITUDE = 0.5


class Selecteur(Protocol):
    """Interface commune au modèle entraîné (voir ``modele.ModeleExtraction``)."""

    version: str

    def predire_entite(self, lignes: list[Ligne]) -> tuple[str, float]: ...

    def choisir_total(self, c: list[CandidatMontant]) -> tuple[CandidatMontant | None, float]: ...

    def choisir_date(self, c: list[CandidatDate]) -> tuple[CandidatDate | None, float]: ...


@dataclass
class ResultatExtraction:
    """Résultat structuré enregistré en base par MS3."""

    entity: str
    date: date | None
    total_amount: Decimal | None
    currency: str | None
    confidence: dict[str, float] = field(default_factory=dict)
    methode: dict[str, str] = field(default_factory=dict)
    champs_manquants: list[str] = field(default_factory=list)
    champs_incertains: list[str] = field(default_factory=list)
    version_modele: str = "regles"

    def en_dict(self) -> dict:
        """Représentation JSON (montant en chaîne pour garder la précision)."""
        return {
            "entity": self.entity,
            "date": self.date.isoformat() if self.date else None,
            "total_amount": str(self.total_amount) if self.total_amount is not None else None,
            "currency": self.currency,
            "confidence": self.confidence,
            "methode": self.methode,
            "champs_manquants": self.champs_manquants,
            "champs_incertains": self.champs_incertains,
            "version_modele": self.version_modele,
        }


def extraire(pages: list[dict], selecteur: Selecteur | None = None,
             aujourd_hui: date | None = None) -> ResultatExtraction:
    """Extrait les trois champs d'un ticket à partir de ses pages OCR.

    Exemple :
        >>> pages = [{"lignes": [
        ...     {"texte": "CARREFOUR", "y_rel": 0.05},
        ...     {"texte": "12/11/2026 à 10h02", "y_rel": 0.2},
        ...     {"texte": "TOTAL A PAYER 42,90 €", "y_rel": 0.7}]}]
        >>> r = extraire(pages, aujourd_hui=date(2026, 11, 16))
        >>> (r.entity, r.date.isoformat(), str(r.total_amount), r.currency)
        ('CARREFOUR', '2026-11-12', '42.90', 'EUR')
    """
    lignes = aplatir(pages)
    montants = candidats_montants(lignes)
    dates = candidats_dates(lignes, aujourd_hui)
    confiance: dict[str, float] = {}
    methode: dict[str, str] = {}

    # --- Entité ---------------------------------------------------------
    entite = INCONNUE
    if selecteur is not None:
        entite, confiance["entity"] = selecteur.predire_entite(lignes)
        methode["entity"] = "modele"
    if entite == INCONNUE:
        # Repli : modèle absent ou incertain (mise en page jamais vue). Si le
        # nom de l'enseigne est écrit en clair, les règles le retrouvent.
        entite_regles, confiance_regles = regles.entite_par_mots_cles(lignes)
        if selecteur is None or entite_regles != INCONNUE:
            entite, confiance["entity"] = entite_regles, confiance_regles
            methode["entity"] = "regles"

    # --- Total ----------------------------------------------------------
    total: CandidatMontant | None = None
    if selecteur is not None:
        total, confiance["total_amount"] = selecteur.choisir_total(montants)
        methode["total_amount"] = "modele"
    if total is None:
        total = regles.total_par_regles(montants)
        confiance["total_amount"] = 0.5 if total else 0.0
        methode["total_amount"] = "regles" if total else "aucun"

    # --- Date -----------------------------------------------------------
    jour: CandidatDate | None = None
    if selecteur is not None:
        jour, confiance["date"] = selecteur.choisir_date(dates)
        methode["date"] = "modele"
    if jour is None:
        jour = regles.date_par_regles(dates)
        confiance["date"] = 0.5 if jour else 0.0
        methode["date"] = "regles" if jour else "aucun"

    valeur_total = total.valeur if total else None
    # La devise n'est renseignée que si elle est justifiée : symbole lu, ou
    # enseigne française reconnue avec un total trouvé.
    texte = " ".join(ligne.norm for ligne in lignes)
    devise_lue = "EUR" in texte or "€" in " ".join(ligne.texte for ligne in lignes)
    devise = "EUR" if valeur_total is not None and (devise_lue or entite != INCONNUE) else None

    resultat = ResultatExtraction(
        entity=entite,
        date=jour.valeur if jour else None,
        total_amount=valeur_total,
        currency=devise,
        confidence={k: round(float(v), 3) for k, v in confiance.items()},
        methode=methode,
        version_modele=selecteur.version if selecteur else "regles",
    )
    if entite == INCONNUE:
        resultat.champs_manquants.append("entity")
    if resultat.date is None:
        resultat.champs_manquants.append("date")
    if resultat.total_amount is None:
        resultat.champs_manquants.append("total_amount")
    resultat.champs_incertains = [
        champ for champ, c in resultat.confidence.items()
        if champ not in resultat.champs_manquants and c < SEUIL_INCERTITUDE
    ]
    return resultat
