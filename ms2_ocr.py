"""MS2 — OCR : lire le texte des images préparées par MS1.

Entrée (file « ocr »)        : {"document_id", "pages": [...]}
Sortie (file « extraction ») : {"document_id", "texte": "CARREFOUR\\n...\\nTOTAL 42,90"}

MS2 ne cherche pas à comprendre le texte : il le lit, c'est tout.
Le texte (quelques Ko) voyage dans le message, car MS3, sur la VM Fedora,
n'a pas accès aux fichiers du Mac.
"""

import os
from pathlib import Path

import pytesseract
from PIL import Image

from commun import attendre_rabbitmq, lancer_service

STOCKAGE = Path(os.environ.get("STOCKAGE", "storage"))


def lire_texte(image):
    """OCR Tesseract en français ; ``--psm 4`` = une colonne de texte, comme un ticket."""
    return pytesseract.image_to_string(image, lang="fra", config="--psm 4")


def traiter(message):
    texte = "\n".join(lire_texte(Image.open(STOCKAGE / page)) for page in message["pages"])
    return "extraction", {**message, "texte": texte}


if __name__ == "__main__":
    attendre_rabbitmq()
    lancer_service("ms2", {"ocr": traiter})
