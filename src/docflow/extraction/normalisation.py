"""Normalisation des valeurs métier : montants, dates, enseignes.

Règle d'or (cahier des charges §4.4 et §6.3) : on ne devine jamais. Une
valeur illisible ou incohérente devient ``None``, pas une valeur plausible.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

ENTITES = ("CARREFOUR", "LIDL", "INTERMARCHE")
INCONNUE = "UNKNOWN"
ANNEE_MIN = 2015

_ESPACES = re.compile(r"[\s  ]+")


def sans_accents(texte: str) -> str:
    """Retire les accents et met en majuscules.

    Exemple :
        >>> sans_accents("Intermarché à payer")
        'INTERMARCHE A PAYER'
    """
    decompose = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in decompose if not unicodedata.combining(c)).upper()


def normaliser_montant(valeur: str) -> Decimal | None:
    """Convertit un montant écrit à la française ou à l'anglaise en ``Decimal``.

    Gère la virgule ou le point décimal, les séparateurs de milliers (espace,
    espace insécable), le symbole € et la mention EUR. Retourne ``None`` si la
    chaîne n'est pas un montant à deux décimales.

    Exemples :
        >>> normaliser_montant("42,90")
        Decimal('42.90')
        >>> normaliser_montant("1 234,56 €")
        Decimal('1234.56')
        >>> normaliser_montant("6.43€")
        Decimal('6.43')
        >>> normaliser_montant("-2,34")
        Decimal('-2.34')
        >>> normaliser_montant("douze") is None
        True

    ``Decimal`` évite les erreurs d'arrondi des flottants (0.1 + 0.2 != 0.3).
    """
    texte = _ESPACES.sub("", valeur).replace("€", "").upper().replace("EUR", "")
    if not re.fullmatch(r"-?\d+[.,]\d{2}", texte):
        return None
    try:
        return Decimal(texte.replace(",", "."))
    except InvalidOperation:
        return None


def normaliser_date(jour: str, mois: str, annee: str, aujourd_hui: date | None = None) -> date | None:
    """Construit une date valide et plausible pour un ticket.

    Les années sur deux chiffres sont ramenées au XXIᵉ siècle. Une date dans
    le futur ou antérieure à ``ANNEE_MIN`` est rejetée.

    Exemples :
        >>> normaliser_date("12", "11", "2026", date(2026, 11, 16))
        datetime.date(2026, 11, 12)
        >>> normaliser_date("03", "10", "23", date(2026, 11, 16))
        datetime.date(2023, 10, 3)
        >>> normaliser_date("31", "02", "2025") is None
        True
    """
    aujourd_hui = aujourd_hui or date.today()
    a = int(annee)
    if a < 100:
        a += 2000
    try:
        resultat = date(a, int(mois), int(jour))
    except ValueError:
        return None
    if resultat.year < ANNEE_MIN or resultat > aujourd_hui:
        return None
    return resultat
