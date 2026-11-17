"""Cœur de MS2 : lire le texte des images préparées avec Tesseract.

Pour chaque page, on reconstruit les **lignes** dans l'ordre de lecture avec,
pour chacune, sa position verticale relative (0 = haut, 1 = bas) et la
confiance moyenne de ses mots. Ces informations servent ensuite à MS3
(ex. « le total est souvent dans la seconde moitié du ticket »).

MS2 ne décide jamais quel montant est le total : il transmet ce qu'il lit
(cahier des charges §4.3).
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

import pytesseract
from PIL import Image

LANGUE = os.environ.get("OCR_LANGUE", "fra")
# psm 4 : « une seule colonne de texte de tailles variables », adapté aux tickets.
CONFIG_TESSERACT = os.environ.get("OCR_CONFIG", "--oem 1 --psm 4")


@dataclass
class LigneOCR:
    """Une ligne de texte reconnue."""

    texte: str
    y_rel: float  # position verticale du haut de la ligne, entre 0 et 1
    confiance: float  # moyenne des confiances Tesseract des mots (0 à 100)


@dataclass
class PageOCR:
    """Résultat OCR d'une page."""

    numero: int
    texte: str
    lignes: list[LigneOCR] = field(default_factory=list)
    nb_mots: int = 0
    confiance_moyenne: float = 0.0
    duree_ms: int = 0

    def en_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1)
def version_tesseract() -> str:
    """Version du moteur, enregistrée avec les mesures pour la reproductibilité."""
    return str(pytesseract.get_tesseract_version())


def regrouper_en_lignes(mots: list[dict]) -> list[list[dict]]:
    """Regroupe les mots qui se chevauchent verticalement en lignes visuelles.

    Tesseract peut couper une même ligne en plusieurs blocs quand un grand
    espace sépare le libellé du montant (« Total à payer ........ 6.43€ »).
    On fusionne donc les mots dont les hauteurs se recouvrent à plus de 50 %,
    puis on les remet dans l'ordre gauche -> droite.

    Exemple :
        >>> m = lambda t, g, h: {"texte": t, "gauche": g, "haut": h, "bas": h + 20}
        >>> [[x["texte"] for x in l] for l in regrouper_en_lignes(
        ...     [m("6.43€", 900, 102), m("Total", 10, 100), m("Payé", 10, 160)])]
        [['Total', '6.43€'], ['Payé']]
    """
    lignes: list[list[dict]] = []
    for mot in sorted(mots, key=lambda m: (m["haut"] + m["bas"]) / 2):
        if lignes:
            derniere = lignes[-1]
            haut = min(m["haut"] for m in derniere)
            bas = max(m["bas"] for m in derniere)
            recouvrement = min(bas, mot["bas"]) - max(haut, mot["haut"])
            plus_petite = min(bas - haut, mot["bas"] - mot["haut"])
            if plus_petite > 0 and recouvrement / plus_petite > 0.5:
                derniere.append(mot)
                continue
        lignes.append([mot])
    return [sorted(ligne, key=lambda m: m["gauche"]) for ligne in lignes]


def lire_page(chemin_image: Path, numero: int = 1) -> PageOCR:
    """Applique l'OCR à une image et regroupe les mots en lignes.

    Exemple :
        image normalisée -> PageOCR(texte="INTERMARCHE\\n...\\nTOTAL 23,40 EUR", ...)

    Une page sans aucun mot détecté est renvoyée avec ``texte == ""`` : c'est à
    l'appelant de la signaler.
    """
    debut = time.perf_counter()
    with Image.open(chemin_image) as image:
        hauteur = image.height
        donnees = pytesseract.image_to_data(
            image, lang=LANGUE, config=CONFIG_TESSERACT, output_type=pytesseract.Output.DICT
        )

    mots = [
        {
            "texte": donnees["text"][i].strip(),
            "conf": float(donnees["conf"][i]),
            "gauche": donnees["left"][i],
            "haut": donnees["top"][i],
            "bas": donnees["top"][i] + donnees["height"][i],
        }
        for i in range(len(donnees["text"]))
        if donnees["text"][i].strip() and float(donnees["conf"][i]) >= 0
    ]
    lignes = regrouper_en_lignes(mots)

    resultat = [
        LigneOCR(
            texte=" ".join(m["texte"] for m in ligne),
            y_rel=round(min(m["haut"] for m in ligne) / max(hauteur, 1), 4),
            confiance=round(sum(m["conf"] for m in ligne) / len(ligne), 1),
        )
        for ligne in lignes
    ]
    toutes_confs = [m["conf"] for m in mots]
    return PageOCR(
        numero=numero,
        texte="\n".join(ligne.texte for ligne in resultat),
        lignes=resultat,
        nb_mots=len(toutes_confs),
        confiance_moyenne=round(sum(toutes_confs) / len(toutes_confs), 1) if toutes_confs else 0.0,
        duree_ms=round((time.perf_counter() - debut) * 1000),
    )


def lire_document(chemins_pages: list[Path]) -> list[PageOCR]:
    """Applique l'OCR à toutes les pages d'un document, dans l'ordre."""
    return [lire_page(chemin, numero) for numero, chemin in enumerate(chemins_pages, start=1)]
