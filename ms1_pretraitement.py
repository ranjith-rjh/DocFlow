"""MS1 — Prétraitement : transformer un PDF ou une image en image(s) propre(s).

Entrée  (file « pretraitement ») : {"document_id", "fichier"}
Sortie  (file « ocr »)           : {"document_id", "pages": ["pretraite/DOC-…/page_1.png", …]}

Étapes, toujours les mêmes quel que soit le format reçu :
    1. PDF -> une image par page ;  image -> chargée telle quelle ;
    2. niveaux de gris ;
    3. agrandissement des petites images (captures d'écran de 412 px) ;
    4. redressement si le ticket est légèrement incliné.
"""

import os
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image

from commun import attendre_rabbitmq, lancer_service

STOCKAGE = Path(os.environ.get("STOCKAGE", "storage"))


def charger_pages(chemin):
    """Retourne la liste des pages du document, en images PIL niveaux de gris."""
    if chemin.suffix == ".pdf":
        try:
            document = pymupdf.open(chemin)
        except Exception:
            raise ValueError("PDF illisible ou corrompu") from None
        pages = []
        for page in document:
            # 300 DPI pour une bonne lecture ; 200 pour les tickets très longs (mémoire).
            dpi = 300 if page.rect.height < 3000 else 200
            pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
            pages.append(Image.frombytes("L", (pix.width, pix.height), pix.samples))
        return pages
    return [Image.open(chemin).convert("L")]


def agrandir(image):
    """Les petites images sont agrandies 4 fois : Tesseract lit mal les petits caractères."""
    if image.width < 1000:
        return image.resize((image.width * 4, image.height * 4), Image.BICUBIC)
    return image


def redresser(image):
    """Corrige une inclinaison de -10° à +10°.

    Idée : quand les lignes de texte sont bien horizontales, la somme des
    pixels noirs par ligne alterne fortement (ligne de texte / interligne).
    On essaie chaque angle et on garde celui où ce contraste est maximal.
    """
    petite = image.copy()
    petite.thumbnail((500, 500))
    encre = np.array(petite) < 128

    def nettete(angle):
        tournee = Image.fromarray(encre).rotate(angle)
        return np.var(np.array(tournee).sum(axis=1))

    meilleur = max(range(-10, 11), key=nettete)
    if meilleur == 0:
        return image
    return image.rotate(meilleur, expand=True, fillcolor=255, resample=Image.BICUBIC)


def traiter(message):
    document_id = message["document_id"]
    dossier = STOCKAGE / "pretraite" / document_id
    dossier.mkdir(parents=True, exist_ok=True)

    pages = []
    for numero, page in enumerate(charger_pages(STOCKAGE / message["fichier"]), start=1):
        page = redresser(agrandir(page))
        chemin = dossier / f"page_{numero}.png"
        page.save(chemin)
        pages.append(str(chemin.relative_to(STOCKAGE)))

    return "ocr", {**message, "pages": pages}


if __name__ == "__main__":
    attendre_rabbitmq()
    lancer_service("ms1", {"pretraitement": traiter})
