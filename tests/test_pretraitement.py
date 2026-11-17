"""Tests de MS1 sur des documents synthétiques (aucun ticket réel)."""

import io

import numpy as np
import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFont

from docflow.pretraitement.traitement import (
    ErreurDocument,
    detecter_format,
    estimer_inclinaison,
    mettre_a_echelle,
    pretraiter,
    redresser,
)


def faux_ticket(largeur: int = 1200, lignes: int = 25) -> np.ndarray:
    """Image blanche avec des lignes de texte noires régulières."""
    image = Image.new("L", (largeur, lignes * 60 + 100), 255)
    dessin = ImageDraw.Draw(image)
    police = ImageFont.load_default(size=36)
    for i in range(lignes):
        dessin.text((60, 50 + i * 60), f"ARTICLE NUMERO {i:02d}      {i},99 EUR", fill=0, font=police)
    return np.array(image)


def en_png(tableau: np.ndarray) -> bytes:
    tampon = io.BytesIO()
    Image.fromarray(tableau).save(tampon, format="PNG")
    return tampon.getvalue()


def pdf_synthetique(pages: int) -> bytes:
    doc = pymupdf.open()
    for i in range(pages):
        p = doc.new_page(width=300, height=600)
        p.insert_text((40, 80), f"TICKET PAGE {i + 1}\nTOTAL 12,34", fontsize=14)
    return doc.tobytes()


def test_detection_du_format_reel():
    assert detecter_format(pdf_synthetique(1)[:16]) == "pdf"
    assert detecter_format(en_png(faux_ticket(200, 2))[:16]) == "png"
    assert detecter_format(b"PK\x03\x04 (un zip renomme en .pdf)") is None


@pytest.mark.parametrize("angle", [-6.0, 4.0])
def test_inclinaison_estimee_et_corrigee(angle):
    incline = redresser(faux_ticket(), angle)
    estime = estimer_inclinaison(incline)
    assert abs(estime + angle) <= 1.0  # l'angle estimé compense l'inclinaison


def test_image_droite_non_modifiee():
    assert estimer_inclinaison(faux_ticket()) == 0.0


def test_petite_capture_agrandie():
    assert mettre_a_echelle(np.zeros((2596, 412), np.uint8)).shape[1] == 1648


def test_pdf_multipage_une_image_par_page(tmp_path):
    r = pretraiter(pdf_synthetique(3), tmp_path)
    assert r.format_source == "pdf"
    assert r.nb_pages == 3
    assert [p.name for p in r.pages] == ["page_001.png", "page_002.png", "page_003.png"]
    for chemin in r.pages:
        with Image.open(chemin) as img:
            assert img.mode == "L" and img.width >= 1000


def test_png_transparent_devient_fond_blanc(tmp_path):
    image = Image.new("RGBA", (500, 300), (0, 0, 0, 0))
    tampon = io.BytesIO()
    image.save(tampon, format="PNG")
    r = pretraiter(tampon.getvalue(), tmp_path)
    with Image.open(r.pages[0]) as img:
        assert np.array(img).mean() > 250


def test_formats_refuses(tmp_path):
    with pytest.raises(ErreurDocument, match="Format non supporté"):
        pretraiter(b"GIF89a....", tmp_path)
    with pytest.raises(ErreurDocument, match="PDF illisible"):
        pretraiter(b"%PDF-1.7 contenu tronque", tmp_path)
    with pytest.raises(ErreurDocument, match="Image illisible"):
        pretraiter(b"\x89PNG\r\n\x1a\n tronque", tmp_path)


def test_trop_de_pages(tmp_path):
    with pytest.raises(ErreurDocument, match="maximum"):
        pretraiter(pdf_synthetique(11), tmp_path)
