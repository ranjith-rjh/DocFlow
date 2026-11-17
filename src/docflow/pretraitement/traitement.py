"""Cœur de MS1 : transformer un document hétérogène en images normalisées.

Décision D-02 : quel que soit le format d'entrée (PDF avec ou sans couche
texte, PNG, JPG), la sortie est **toujours** la même : une image PNG en niveaux
de gris par page, d'une largeur comprise entre ``LARGEUR_MIN`` et
``LARGEUR_MAX`` pixels. La couche texte des PDF n'est jamais transmise à l'OCR.

Étapes, volontairement mesurées pour ne pas abîmer les caractères :
    1. détection du format réel (octets magiques, pas l'extension) ;
    2. PDF -> une image par page (rendu à ``DPI_PDF``) ; image -> chargement
       avec respect de l'orientation EXIF ;
    3. niveaux de gris ;
    4. mise à l'échelle (les captures d'application de 412 px sont agrandies) ;
    5. redressement des petites inclinaisons (±15°) par profil de projection ;
    6. étirement du contraste (pas de binarisation destructrice).
"""

from __future__ import annotations

import io
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from PIL import Image, ImageOps

from docflow.commun.formats import detecter_format

DPI_PDF = int(os.environ.get("PRETRAITEMENT_DPI", "300"))  # 300 : CER Carrefour 11,4 % -> 6,5 %
LARGEUR_MIN = 1000
LARGEUR_CIBLE_AGRANDISSEMENT = int(os.environ.get("PRETRAITEMENT_LARGEUR_AGRANDIE", "1648"))
LARGEUR_MAX = 2400
MAX_PAGES = 10
MAX_PIXELS = 60_000_000  # protection contre les « bombes de décompression »
ANGLE_MAX = 15.0
PAS_ANGLE = 0.5

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class ErreurDocument(ValueError):
    """Document illisible ou hors limites : erreur définitive, inutile de réessayer."""


@dataclass
class ResultatPretraitement:
    """Sortie de MS1 pour un document."""

    pages: list[Path]
    format_source: str
    nb_pages: int
    duree_ms: int
    angles: list[float] = field(default_factory=list)
    largeurs: list[int] = field(default_factory=list)


DPI_MIN = 100


def dpi_page(largeur_pt: float, hauteur_pt: float) -> int:
    """Résolution de rendu d'une page PDF.

    ``DPI_PDF`` en temps normal ; résolution réduite pour les pages très
    longues (tickets Intermarché de plus d'un mètre de « papier » virtuel)
    afin de rester sous ``MAX_PIXELS``. Ces pages sont de toute façon
    ramenées ensuite à ``LARGEUR_MAX`` pixels de large.

    Exemples :
        >>> dpi_page(612, 792)       # page A4/Letter : résolution normale
        300
        >>> dpi_page(780, 5000)      # ticket très long : résolution réduite
        275
    """
    pouces_carres = (largeur_pt / 72) * (hauteur_pt / 72)
    dpi_max = int((MAX_PIXELS * 0.95 / pouces_carres) ** 0.5)
    dpi = min(DPI_PDF, dpi_max)
    if dpi < DPI_MIN:
        raise ErreurDocument("Page PDF trop grande")
    return dpi


def charger_pages(contenu: bytes, format_source: str) -> list[np.ndarray]:
    """Convertit le document en liste d'images en niveaux de gris (une par page)."""
    if format_source == "pdf":
        try:
            doc = pymupdf.open(stream=contenu, filetype="pdf")
        except Exception as exc:  # PyMuPDF lève plusieurs types d'exceptions
            raise ErreurDocument("PDF illisible ou corrompu") from exc
        if doc.page_count == 0:
            raise ErreurDocument("PDF sans page")
        if doc.page_count > MAX_PAGES:
            raise ErreurDocument(f"PDF de {doc.page_count} pages (maximum {MAX_PAGES})")
        pages = []
        for page in doc:
            pix = page.get_pixmap(dpi=dpi_page(page.rect.width, page.rect.height),
                                  colorspace=pymupdf.csGRAY, alpha=False)
            tableau = np.frombuffer(pix.samples, dtype=np.uint8)
            pages.append(tableau.reshape(pix.height, pix.stride)[:, : pix.width].copy())
        return pages

    try:
        image = Image.open(io.BytesIO(contenu))
        image.load()
    except Exception as exc:  # Pillow : formats corrompus, bombes de décompression…
        raise ErreurDocument("Image illisible ou corrompue") from exc
    image = ImageOps.exif_transpose(image)  # photos de téléphone tournées
    if image.mode in ("RGBA", "LA", "P"):
        # Fond transparent -> blanc, sinon il devient noir en niveaux de gris.
        fond = Image.new("RGB", image.size, "white")
        fond.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[-1])
        image = fond
    return [np.array(image.convert("L"))]


def mettre_a_echelle(image: np.ndarray) -> np.ndarray:
    """Ramène la largeur dans ``[LARGEUR_MIN, LARGEUR_MAX]``.

    Les captures Lidl (412 px, caractères de ~10 px) sont agrandies 4 fois
    (~1648 px) : Tesseract lit mal les petits caractères. Valeur choisie sur train + validation.

    Exemple :
        >>> mettre_a_echelle(np.zeros((100, 412), np.uint8)).shape
        (400, 1648)
    """
    hauteur, largeur = image.shape[:2]
    if largeur < LARGEUR_MIN:
        facteur = LARGEUR_CIBLE_AGRANDISSEMENT / largeur
        interpolation = cv2.INTER_CUBIC
    elif largeur > LARGEUR_MAX:
        facteur = LARGEUR_MAX / largeur
        interpolation = cv2.INTER_AREA
    else:
        return image
    taille = (round(largeur * facteur), round(hauteur * facteur))
    return cv2.resize(image, taille, interpolation=interpolation)


def _score_projection(encre: np.ndarray, angle: float) -> float:
    """Netteté du profil horizontal après rotation : maximale quand les lignes
    de texte sont parfaitement horizontales."""
    h, w = encre.shape
    matrice = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    tournee = cv2.warpAffine(encre, matrice, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
    profil = tournee.sum(axis=1, dtype=np.float64)
    return float(np.var(np.diff(profil)))


def estimer_inclinaison(image: np.ndarray) -> float:
    """Estime l'angle (en degrés) qui remet les lignes de texte à l'horizontale.

    Recherche exhaustive par pas de 0,5° sur une version réduite de l'image :
    simple, robuste pour des tickets, et sans dépendre de l'OCR.
    """
    reduite = image
    if image.shape[1] > 600:
        facteur = 600 / image.shape[1]
        reduite = cv2.resize(image, None, fx=facteur, fy=facteur, interpolation=cv2.INTER_AREA)
    _, encre = cv2.threshold(reduite, 0, 1, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    angles = np.arange(-ANGLE_MAX, ANGLE_MAX + PAS_ANGLE / 2, PAS_ANGLE)
    scores = [_score_projection(encre, a) for a in angles]
    meilleur = float(angles[int(np.argmax(scores))])
    # On ne corrige que si le gain est net par rapport à « ne rien faire ».
    score_zero = scores[int(np.argmin(np.abs(angles)))]
    if abs(meilleur) < PAS_ANGLE or max(scores) < score_zero * 1.05:
        return 0.0
    return meilleur


def redresser(image: np.ndarray, angle: float) -> np.ndarray:
    """Tourne l'image de ``angle`` degrés en agrandissant le cadre (fond blanc)."""
    if angle == 0.0:
        return image
    h, w = image.shape
    matrice = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(matrice[0, 0]), abs(matrice[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    matrice[0, 2] += nw / 2 - w / 2
    matrice[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(image, matrice, (nw, nh), flags=cv2.INTER_CUBIC, borderValue=255)


def etirer_contraste(image: np.ndarray) -> np.ndarray:
    """Étire les niveaux entre les percentiles 1 et 99 (impressions pâles).

    Exemple :
        >>> img = np.array([[100, 150], [150, 200]], np.uint8)
        >>> int(etirer_contraste(img).max())
        255
    """
    bas, haut = np.percentile(image, (1, 99))
    if haut - bas < 10:  # page uniforme : rien à étirer
        return image
    etiree = (image.astype(np.float32) - bas) * (255.0 / (haut - bas))
    return np.clip(etiree, 0, 255).astype(np.uint8)


def normaliser_page(image: np.ndarray) -> tuple[np.ndarray, float]:
    """Applique mise à l'échelle, redressement et contraste à une page."""
    image = mettre_a_echelle(image)
    angle = estimer_inclinaison(image)
    image = redresser(image, angle)
    return etirer_contraste(image), angle


def pretraiter(contenu: bytes, dossier_sortie: Path) -> ResultatPretraitement:
    """Prétraite un document complet et écrit ``page_001.png``, ``page_002.png``…

    Exemple :
        ``ticket_lidl.png`` -> ``storage/pretraite/DOC-0002/page_001.png``

    Lève :class:`ErreurDocument` pour un format non supporté, un fichier
    corrompu ou un dépassement des limites.
    """
    debut = time.perf_counter()
    format_source = detecter_format(contenu[:16])
    if format_source is None:
        raise ErreurDocument("Format non supporté (PDF, PNG ou JPEG attendu)")

    dossier_sortie.mkdir(parents=True, exist_ok=True)
    chemins, angles, largeurs = [], [], []
    for numero, page in enumerate(charger_pages(contenu, format_source), start=1):
        normalisee, angle = normaliser_page(page)
        chemin = dossier_sortie / f"page_{numero:03d}.png"
        cv2.imwrite(str(chemin), normalisee)
        chemins.append(chemin)
        angles.append(angle)
        largeurs.append(int(normalisee.shape[1]))

    return ResultatPretraitement(
        pages=chemins,
        format_source=format_source,
        nb_pages=len(chemins),
        duree_ms=round((time.perf_counter() - debut) * 1000),
        angles=angles,
        largeurs=largeurs,
    )
