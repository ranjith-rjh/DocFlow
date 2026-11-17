"""Tests du parseur de noms et du découpage du corpus (fichiers fictifs)."""

from collections import Counter
from datetime import date
from decimal import Decimal

import pytest

from training.corpus import NomInvalide, construire_annotations, decouper, lire_nom


def test_lecture_du_nom_annee_jour_mois():
    assert lire_nom("carrefour_2025-17-04_12.34.pdf") == (
        "CARREFOUR", date(2025, 4, 17), Decimal('12.34'), None)


@pytest.mark.parametrize("nom", ["carrefour_2025-04-17.pdf", "auchan_2025-17-04_1.00.pdf",
                                 "lidl_2025-31-02_1.00.png", "lidl_2025-17-04_1,00.png"])
def test_noms_invalides(nom):
    with pytest.raises(NomInvalide):
        lire_nom(nom)


def creer(dossier, *noms):
    for nom in noms:
        entite = nom.split("_")[0]
        (dossier / entite).mkdir(exist_ok=True)
        (dossier / entite / nom).write_bytes(b"x")


def test_quasi_doublons_dans_le_meme_groupe(tmp_path):
    creer(tmp_path, "carrefour_2026-09-01_99.00.pdf", "carrefour_2026-10-01_99.00.pdf",
          "carrefour_2026-25-01_99.00.pdf", "lidl_2024-01-01_3.00.png")
    groupes = {a.fichier: a.groupe for a in construire_annotations(tmp_path)}
    assert groupes["carrefour/carrefour_2026-09-01_99.00.pdf"] == \
        groupes["carrefour/carrefour_2026-10-01_99.00.pdf"]
    assert groupes["carrefour/carrefour_2026-25-01_99.00.pdf"] != \
        groupes["carrefour/carrefour_2026-09-01_99.00.pdf"]


def test_decoupage_stratifie_et_deterministe(tmp_path):
    noms = [f"lidl_2024-{j:02d}-01_{j}.00.png" for j in range(1, 21)]
    noms += [f"intermarche_2025-{j:02d}-02_{j}.50.pdf" for j in range(1, 8)]
    creer(tmp_path, *noms)
    annotations = construire_annotations(tmp_path)
    p1, p2 = decouper(annotations), decouper(annotations)
    assert p1 == p2
    par_entite = Counter((a.entity, p1[a.groupe]) for a in annotations)
    for entite in ("LIDL", "INTERMARCHE"):
        for partition in ("train", "validation", "test"):
            assert par_entite[(entite, partition)] >= 1
