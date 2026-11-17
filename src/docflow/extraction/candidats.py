"""Génération des candidats « date » et « montant » à partir des lignes OCR.

Un ticket contient de nombreux montants (articles, remises, TVA, sous-totaux)
et parfois plusieurs dates. Plutôt que de chercher directement « le » total,
on liste **tous** les candidats avec leur contexte, puis on choisit :
    * par règles (baseline, ``regles.py``) ;
    * ou par un classifieur entraîné (``modele.py``).

Cette séparation candidats / sélection est la base de l'approche hybride
documentée (cahier des charges §4.4 et §8.4) : la génération est
déterministe, la sélection est apprise.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from docflow.extraction.normalisation import normaliser_date, normaliser_montant, sans_accents

# Montant à deux décimales, non collé à d'autres chiffres (exclut 02.04.25,
# les pourcentages 5,50 % et les numéros longs).
MOTIF_MONTANT = re.compile(
    r"(?<![\d.,/])(-?\d{1,4}(?:[  ]\d{3})*[.,]\d{2})(?![\d.,/]|\s?%)"
)
MOTIF_DATE = re.compile(r"(?<![\d/.\-])(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})(?![\d/.\-])")
MOTIF_HEURE = re.compile(r"\b\d{1,2}\s?[:hH]\s?\d{2}\b")


@dataclass
class Ligne:
    """Ligne OCR aplatie sur l'ensemble du document."""

    texte: str
    norm: str  # texte sans accents en majuscules
    page: int
    index: int  # rang global de la ligne dans le document
    y_doc: float  # position verticale globale entre 0 et 1 (toutes pages)


@dataclass
class CandidatMontant:
    valeur: Decimal
    ligne: Ligne
    rang_dans_ligne: int
    nb_dans_ligne: int
    precedente: str  # texte normalisé de la ligne précédente
    suivante: str


@dataclass
class CandidatDate:
    valeur: date
    ligne: Ligne
    annee_4_chiffres: bool
    heure_sur_ligne: bool


def aplatir(pages: list[dict]) -> list[Ligne]:
    """Transforme les pages OCR (format du message ``ocr.completed``) en lignes.

    ``pages`` : ``[{"numero": 1, "lignes": [{"texte": ..., "y_rel": ...}, ...]}, ...]``
    """
    lignes: list[Ligne] = []
    nb_pages = max(len(pages), 1)
    for p, page in enumerate(pages):
        for ligne in page.get("lignes", []):
            texte = ligne["texte"]
            lignes.append(
                Ligne(
                    texte=texte,
                    norm=sans_accents(texte),
                    page=p + 1,
                    index=len(lignes),
                    y_doc=(p + float(ligne.get("y_rel", 0.0))) / nb_pages,
                )
            )
    return lignes


def candidats_montants(lignes: list[Ligne]) -> list[CandidatMontant]:
    """Liste tous les montants lus, avec leur ligne et leurs voisines.

    Exemple :
        >>> l = aplatir([{"lignes": [{"texte": "TOTAL TTC : 42,90 €", "y_rel": 0.8}]}])
        >>> [str(c.valeur) for c in candidats_montants(l)]
        ['42.90']
    """
    resultats = []
    for i, ligne in enumerate(lignes):
        trouves = [normaliser_montant(m) for m in MOTIF_MONTANT.findall(ligne.texte)]
        trouves = [v for v in trouves if v is not None]
        for rang, valeur in enumerate(trouves):
            resultats.append(
                CandidatMontant(
                    valeur=valeur,
                    ligne=ligne,
                    rang_dans_ligne=rang,
                    nb_dans_ligne=len(trouves),
                    precedente=lignes[i - 1].norm if i > 0 else "",
                    suivante=lignes[i + 1].norm if i + 1 < len(lignes) else "",
                )
            )
    return resultats


def candidats_dates(lignes: list[Ligne], aujourd_hui: date | None = None) -> list[CandidatDate]:
    """Liste toutes les dates plausibles lues sur le ticket.

    Exemple :
        >>> l = aplatir([{"lignes": [{"texte": "LE 03-10-23 A 18-33-22", "y_rel": 0.5}]}])
        >>> [c.valeur.isoformat() for c in candidats_dates(l, date(2026, 1, 1))]
        ['2023-10-03']
    """
    resultats = []
    for ligne in lignes:
        for jour, mois, annee in MOTIF_DATE.findall(ligne.texte):
            valeur = normaliser_date(jour, mois, annee, aujourd_hui)
            if valeur is None:
                continue
            resultats.append(
                CandidatDate(
                    valeur=valeur,
                    ligne=ligne,
                    annee_4_chiffres=len(annee) == 4,
                    heure_sur_ligne=bool(MOTIF_HEURE.search(ligne.texte)),
                )
            )
    return resultats


def frequences(valeurs: list) -> Counter:
    """Nombre d'occurrences de chaque valeur (le total apparaît souvent 2 à 4 fois)."""
    return Counter(valeurs)
