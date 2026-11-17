"""Tests de la génération de candidats et de la baseline, sur des tickets fictifs."""

from datetime import date
from decimal import Decimal

from docflow.extraction.candidats import aplatir, candidats_dates, candidats_montants
from docflow.extraction.extracteur import extraire

AUJOURDHUI = date(2026, 11, 16)


def page(*textes: str) -> list[dict]:
    n = len(textes)
    return [{"numero": 1, "lignes": [{"texte": t, "y_rel": i / n} for i, t in enumerate(textes)]}]


def test_montants_ignore_dates_pourcentages_et_numeros():
    lignes = aplatir(page("02.04.25 12:21 8009", "5,50% 13,38", "Carte 9135720000917563243",
                          "1 x 1.75 1.75"))
    valeurs = [str(c.valeur) for c in candidats_montants(lignes)]
    assert valeurs == ["13.38", "1.75", "1.75"]


def test_dates_formats_courants():
    lignes = aplatir(page("02/04/2025 à 12h21", "LE 03-10-23 A 18-33-22", "22.07.2025",
                          "ref 219980/05/13/02"))
    valeurs = [c.valeur.isoformat() for c in candidats_dates(lignes, AUJOURDHUI)]
    assert valeurs == ["2025-04-02", "2023-10-03", "2025-07-22"]


def test_total_evite_sous_total_et_total_eligible():
    pages = page(
        "INTERMARCHE",
        "PAT GOUDA 1,97 EUR A",
        "MONTANT DU 16,11 EUR",
        "TOTAL ELIGIBLE TRD 14,12 EUR",
        "TOTAL TVA 15,04 1,07 16,11",
        "22/07/2025 16:59:52",
    )
    r = extraire(pages, aujourd_hui=AUJOURDHUI)
    assert r.entity == "INTERMARCHE"
    assert r.total_amount == Decimal("16.11")
    assert r.date == date(2025, 7, 22)
    assert r.currency == "EUR"
    assert r.champs_manquants == []


def test_ticket_vide_ne_devine_rien():
    r = extraire([{"numero": 1, "lignes": []}], aujourd_hui=AUJOURDHUI)
    assert (r.entity, r.date, r.total_amount, r.currency) == ("UNKNOWN", None, None, None)
    assert set(r.champs_manquants) == {"entity", "date", "total_amount"}
    assert r.methode["total_amount"] == "aucun"


def test_erreurs_ocr_legeres_sur_enseigne():
    r = extraire(page("CARREF0UR market", "TOTAL 3,00"), aujourd_hui=AUJOURDHUI)
    assert r.entity == "CARREFOUR"


def test_multipage_conserve_l_ordre():
    pages = [
        {"numero": 1, "lignes": [{"texte": "LIDL", "y_rel": 0.1}, {"texte": "Lait 1,20", "y_rel": 0.5}]},
        {"numero": 2, "lignes": [{"texte": "A payer 8,40", "y_rel": 0.2}]},
    ]
    lignes = aplatir(pages)
    assert [ligne.page for ligne in lignes] == [1, 1, 2]
    assert lignes[2].y_doc > lignes[1].y_doc
    assert extraire(pages, aujourd_hui=AUJOURDHUI).total_amount == Decimal("8.40")


class SelecteurIncertain:
    """Simule un modèle qui ne reconnaît pas la mise en page."""

    version = "test"

    def predire_entite(self, lignes):
        return "UNKNOWN", 0.4

    def choisir_total(self, candidats):
        return (candidats[-1], 0.9) if candidats else (None, 0.0)

    def choisir_date(self, candidats):
        return (candidats[0], 0.8) if candidats else (None, 0.0)


def test_repli_sur_regles_si_modele_incertain():
    r = extraire(page("LIDL", "A payer 8,40", "03.10.25 18:33"), SelecteurIncertain(),
                 aujourd_hui=AUJOURDHUI)
    assert (r.entity, r.methode["entity"]) == ("LIDL", "regles")
    assert r.methode["total_amount"] == "modele" and r.version_modele == "test"


def test_modele_incertain_sans_nom_reste_inconnu():
    r = extraire(page("SAS CALAO", "MONTANT DU 16,11 EUR"), SelecteurIncertain(),
                 aujourd_hui=AUJOURDHUI)
    assert r.entity == "UNKNOWN" and "entity" in r.champs_manquants
