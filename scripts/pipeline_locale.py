"""Pipeline monolithique : un fichier -> JSON, sans réseau ni messagerie (DF-07).

Sert de prototype (phase P2) et de **référence** pour comparer le surcoût de
la version distribuée (§11.2). Les trois étapes sont exactement les mêmes
fonctions que celles de MS1, MS2 et MS3.

Usage (image « outils », Tesseract français inclus) :
    docker compose run --rm outils python scripts/pipeline_locale.py data/raw/lidl/xxx.png
    docker compose run --rm outils python scripts/pipeline_locale.py --repetitions 3 <fichiers...>
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

from docflow.extraction.extracteur import extraire
from docflow.ocr.moteur import lire_document
from docflow.pretraitement.traitement import pretraiter


def charger_selecteur():
    """Charge le modèle entraîné si ``MODELE_CHEMIN`` pointe vers un artefact."""
    chemin = os.environ.get("MODELE_CHEMIN")
    if not chemin or not Path(chemin).exists():
        return None
    from docflow.extraction.modele import ModeleExtraction

    return ModeleExtraction.charger(Path(chemin))


def traiter(chemin: Path, selecteur=None) -> dict:
    """Exécute MS1 -> MS2 -> MS3 en mémoire et retourne le résultat + durées."""
    debut = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        pre = pretraiter(chemin.read_bytes(), Path(tmp))
        t_ocr = time.perf_counter()
        pages = lire_document(pre.pages)
        duree_ocr = round((time.perf_counter() - t_ocr) * 1000)
    t_ext = time.perf_counter()
    resultat = extraire([p.en_dict() for p in pages], selecteur)
    duree_ext = round((time.perf_counter() - t_ext) * 1000)
    return {
        **resultat.en_dict(),
        "duree_ms": {"ms1": pre.duree_ms, "ms2": duree_ocr, "ms3": duree_ext,
                     "total": round((time.perf_counter() - debut) * 1000)},
    }


def main() -> None:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("fichiers", nargs="+", type=Path)
    parseur.add_argument("--repetitions", type=int, default=1)
    parseur.add_argument("--resume", action="store_true", help="n'affiche que les durées")
    args = parseur.parse_args()
    selecteur = charger_selecteur()
    durees = []
    for _ in range(args.repetitions):
        for fichier in args.fichiers:
            r = traiter(fichier, selecteur)
            durees.append(r["duree_ms"]["total"])
            if not args.resume:
                print(json.dumps(r, ensure_ascii=False, indent=2))
    if args.resume:
        durees.sort()
        print(json.dumps({"n": len(durees), "moyenne_ms": round(sum(durees) / len(durees)),
                          "mediane_ms": durees[len(durees) // 2],
                          "debit_docs_min": round(60000 * len(durees) / sum(durees), 1)}))


if __name__ == "__main__":
    main()
