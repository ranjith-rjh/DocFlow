"""Fabrique de tickets synthétiques pour les tests d'intégration.

Aucun ticket réel n'est utilisé dans les tests versionnés (confidentialité) :
on dessine des tickets fictifs avec Pillow / PyMuPDF.
"""

from __future__ import annotations

import io

import pymupdf
from PIL import Image, ImageDraw, ImageFont


def image_ticket(lignes: list[str], angle: float = 0.0, format_: str = "PNG") -> bytes:
    """Ticket fictif en image ; ``angle`` simule une photo inclinée (T-02)."""
    police = ImageFont.load_default(size=40)
    image = Image.new("L", (1100, 120 + 62 * len(lignes)), 255)
    dessin = ImageDraw.Draw(image)
    for i, texte in enumerate(lignes):
        dessin.text((70, 60 + i * 62), texte, fill=0, font=police)
    if angle:
        image = image.rotate(angle, expand=True, fillcolor=255, resample=Image.BICUBIC)
    tampon = io.BytesIO()
    image.save(tampon, format=format_)
    return tampon.getvalue()


def pdf_ticket(pages: list[list[str]]) -> bytes:
    """Ticket fictif en PDF, une liste de lignes par page (T-03, T-04)."""
    doc = pymupdf.open()
    for lignes in pages:
        page = doc.new_page(width=300, height=40 + 22 * len(lignes) + 40)
        for i, texte in enumerate(lignes):
            page.insert_text((24, 40 + i * 22), texte, fontname="cour", fontsize=11)
    return doc.tobytes()


TICKET_CARREFOUR = [
    "CARREFOUR MARKET",
    "12 RUE DE LA GARE",
    "05/11/2026 a 10h42",
    "PAIN DE MIE          1,20",
    "LAIT DEMI ECREME     0,99",
    "BEURRE DOUX          2,35",
    "Total a payer        4,54 EUR",
    "Carte bancaire       4,54 EUR",
]

TICKET_AMBIGU = [
    "LIDL",
    "Article         P.U.EUR   EUR",
    "Fromage rape       1,98   3,96",
    "Reduction Lidl Plus      -0,94",
    "Sous-total               3,02",
    "A payer                  3,02",
    "Total Promotion          0,94",
    "TOTAL ELIGIBLE TRD       3,96",
    "03.10.25 18:33:45",
]
