"""Passe le corpus complet dans MS1 + MS2 (hors ligne) et met le résultat en cache.

Le texte OCR ainsi obtenu est exactement celui que recevra MS3 en production :
c'est sur lui que l'on construit les candidats d'entraînement et que l'on
évalue. Exécuter l'OCR sur le jeu de test n'est pas une fuite : l'OCR ne
s'entraîne pas, seul le modèle d'extraction apprend (et uniquement sur
``train`` + ``validation``).

Produit (dossiers ignorés par Git, contenu privé) :
    data/interim/ocr/<nom>.json        pages et lignes OCR
    data/interim/reference/<nom>.txt   couche texte des PDF (référence CER/WER)

Usage (dans l'image « outils », qui contient Tesseract français) :
    docker compose run --rm outils python -m training.ocr_corpus
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pymupdf

from docflow.ocr.moteur import lire_document, version_tesseract
from docflow.pretraitement.traitement import pretraiter
from training.corpus import DOSSIER_BRUT, charger_annotations

DOSSIER_OCR = Path("data/interim/ocr")
DOSSIER_REFERENCE = Path("data/interim/reference")


def traiter(fichier: str) -> tuple[str, int, int, int]:
    """Prétraite et lit un fichier ; retourne (fichier, pages, ms MS1, ms MS2)."""
    source = DOSSIER_BRUT / fichier
    contenu = source.read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        pre = pretraiter(contenu, Path(tmp))
        debut = time.perf_counter()
        pages = lire_document(pre.pages)
        duree_ocr = round((time.perf_counter() - debut) * 1000)
    sortie = DOSSIER_OCR / (Path(fichier).stem + ".json")
    sortie.write_text(
        json.dumps({"fichier": fichier, "pages": [p.en_dict() for p in pages],
                    "duree_ms": {"ms1": pre.duree_ms, "ms2": duree_ocr},
                    "angles": pre.angles}, ensure_ascii=False),
        encoding="utf-8",
    )
    if source.suffix == ".pdf":
        doc = pymupdf.open(stream=contenu, filetype="pdf")
        texte = "\n".join(page.get_text(sort=True) for page in doc)
        (DOSSIER_REFERENCE / (Path(fichier).stem + ".txt")).write_text(texte, encoding="utf-8")
    return fichier, pre.nb_pages, pre.duree_ms, duree_ocr


def main() -> None:
    DOSSIER_OCR.mkdir(parents=True, exist_ok=True)
    DOSSIER_REFERENCE.mkdir(parents=True, exist_ok=True)
    fichiers = [ligne["fichier"] for ligne in charger_annotations()]
    if len(sys.argv) > 1:  # sous-ensemble pour les essais : python -m ... lidl
        fichiers = [f for f in fichiers if sys.argv[1] in f]
    # Le cache de chaque fichier traité est d'abord supprimé : un échec laisse
    # un trou (qui fera échouer l'évaluation) plutôt qu'un résultat périmé.
    for f in fichiers:
        (DOSSIER_OCR / (Path(f).stem + ".json")).unlink(missing_ok=True)
    print(f"Tesseract {version_tesseract()} — {len(fichiers)} fichiers")
    debut = time.perf_counter()
    with ProcessPoolExecutor(max_workers=int(os.environ.get("NB_PROCESSUS", "6"))) as pool:
        taches = {pool.submit(traiter, f): f for f in fichiers}
        echecs = []
        for i, tache in enumerate(as_completed(taches), start=1):
            try:
                fichier, nb, t1, t2 = tache.result()
                print(f"[{i:3d}/{len(fichiers)}] {Path(fichier).parent.name:<11} pages={nb} "
                      f"ms1={t1}ms ms2={t2}ms")
            except Exception as exc:  # noqa: BLE001 - on veut tout signaler
                echecs.append(taches[tache])
                print(f"[{i:3d}/{len(fichiers)}] ÉCHEC {Path(taches[tache]).parent.name} : {exc}")
    print(f"Terminé en {time.perf_counter() - debut:.1f} s, {len(echecs)} échec(s)")
    if echecs:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
