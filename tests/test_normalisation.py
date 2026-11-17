"""Tests des normalisations : les erreurs ici faussent toute l'évaluation."""

from datetime import date
from decimal import Decimal

import pytest

from docflow.extraction.normalisation import normaliser_date, normaliser_montant, sans_accents


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("42,90", Decimal("42.90")),
        ("42.90", Decimal("42.90")),
        ("6.43€", Decimal("6.43")),
        ("16,11 EUR", Decimal("16.11")),
        ("1 234,56", Decimal("1234.56")),
        ("1 234,56 €", Decimal("1234.56")),
        ("-2,34", Decimal("-2.34")),
        ("0,00", Decimal("0.00")),
    ],
)
def test_montants_valides(texte, attendu):
    assert normaliser_montant(texte) == attendu


@pytest.mark.parametrize("texte", ["", "abc", "42", "42,9", "4,2,90", "5.5%", "12:30"])
def test_montants_invalides_donnent_none(texte):
    assert normaliser_montant(texte) is None


def test_decimal_evite_les_erreurs_de_flottant():
    assert normaliser_montant("0,10") + normaliser_montant("0,20") == Decimal("0.30")


AUJOURDHUI = date(2026, 11, 16)


@pytest.mark.parametrize(
    ("j", "m", "a", "attendu"),
    [
        ("12", "11", "2026", date(2026, 11, 12)),
        ("3", "10", "23", date(2023, 10, 3)),
        ("29", "02", "2024", date(2024, 2, 29)),
    ],
)
def test_dates_valides(j, m, a, attendu):
    assert normaliser_date(j, m, a, AUJOURDHUI) == attendu


@pytest.mark.parametrize(
    ("j", "m", "a"),
    [("31", "02", "2025"), ("12", "13", "2025"), ("01", "01", "2010"), ("17", "11", "2026")],
)
def test_dates_impossibles_futures_ou_trop_anciennes(j, m, a):
    assert normaliser_date(j, m, a, AUJOURDHUI) is None


def test_sans_accents():
    assert sans_accents("Intermarché — à payer") == "INTERMARCHE — A PAYER"
