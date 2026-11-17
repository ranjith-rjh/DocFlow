"""Tests des références de stockage et du regroupement des mots OCR."""

from pathlib import Path

import pytest

from docflow.commun.stockage import ReferenceInvalide, vers_chemin, vers_reference
from docflow.ocr.moteur import regrouper_en_lignes


def test_aller_retour_reference(tmp_path):
    chemin = tmp_path / "pretraite" / "DOC-1" / "page_001.png"
    ref = vers_reference(chemin, tmp_path)
    assert ref == "storage://pretraite/DOC-1/page_001.png"
    assert vers_chemin(ref, tmp_path) == chemin.resolve()


@pytest.mark.parametrize("ref", ["storage://../secret", "file:///etc/passwd", "storage:///etc/passwd"])
def test_reference_hors_stockage_refusee(tmp_path, ref):
    with pytest.raises(ReferenceInvalide):
        vers_chemin(ref, tmp_path)


def test_mots_eloignes_sur_la_meme_ligne_sont_fusionnes():
    def mot(texte, gauche, haut, hauteur=30):
        return {"texte": texte, "gauche": gauche, "haut": haut, "bas": haut + hauteur, "conf": 90}

    lignes = regrouper_en_lignes([
        mot("6.43€", 1100, 905), mot("Total", 360, 900), mot("à", 470, 902),
        mot("payer", 500, 900), mot("Payé", 360, 980),
    ])
    assert [" ".join(m["texte"] for m in ligne) for ligne in lignes] == ["Total à payer 6.43€", "Payé"]


def test_reference_racine_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert vers_chemin("storage://a.png", Path(".")) == (tmp_path / "a.png").resolve()
