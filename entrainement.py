"""Entraînement et évaluation du modèle d'enseigne (hors ligne).

Usage (dans Docker, qui contient Tesseract français) :
    docker compose run --rm outils python entrainement.py

Étapes :
    1. les annotations viennent des noms de fichiers :
       carrefour_2025-17-04_12.34.pdf -> CARREFOUR, 17/04/2025, 12.34 €
    2. chaque ticket passe par le code de MS1 + MS2 (texte mis en cache) ;
    3. découpage 80 % entraînement / 20 % test, équilibré par enseigne ;
    4. entraînement du modèle sur les 80 % ;
    5. sur les 20 % de test, jamais vus : règles seules contre modèle ;
    6. sauvegarde du modèle (models/) et du rapport (reports/evaluation.md).
"""

import re
from datetime import date
from decimal import Decimal
from multiprocessing import Pool
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline

from ms1_pretraitement import agrandir, charger_pages, redresser
from ms2_ocr import lire_texte
from ms3_extraction import extraire, preparer_texte

TICKETS = Path("data/raw")
CACHE = Path("data/textes")
NOM = re.compile(r"(carrefour|lidl|intermarche)_(\d{4})-(\d{2})-(\d{2})_(\d+\.\d{2})")


def annotation(fichier):
    """Vérité de référence lue dans le nom : <entite>_<AAAA>-<JJ>-<MM>_<montant>."""
    entite, annee, jour, mois, total = NOM.match(fichier.name).groups()
    return {"entity": entite.upper(), "date": date(int(annee), int(mois), int(jour)),
            "total_amount": Decimal(total)}


def texte_ocr(fichier):
    """Texte du ticket, exactement comme MS1 + MS2 le produiraient (avec cache)."""
    cache = CACHE / (fichier.stem + ".txt")
    if not cache.exists():
        pages = [redresser(agrandir(p)) for p in charger_pages(fichier)]
        cache.write_text("\n".join(lire_texte(p) for p in pages))
    return cache.read_text()


def exactitude(resultats, tickets, champ, enseigne=None):
    """Part des tickets (d'une enseigne, ou tous) dont le champ est juste."""
    paires = [(r, t) for r, t in zip(resultats, tickets) if enseigne in (None, t["entity"])]
    return sum(r[champ] == t[champ] for r, t in paires) / len(paires), len(paires)


if __name__ == "__main__":
    fichiers = sorted(f for f in TICKETS.rglob("*") if NOM.match(f.name))
    tickets = [annotation(f) for f in fichiers]
    CACHE.mkdir(parents=True, exist_ok=True)
    print(f"OCR de {len(fichiers)} tickets (mis en cache dans {CACHE})…")
    with Pool() as pool:
        textes = pool.map(texte_ocr, fichiers)

    # Découpage figé (random_state) et stratifié : chaque enseigne dans les deux groupes.
    i_train, i_test = train_test_split(range(len(tickets)), test_size=0.2, random_state=42,
                                       stratify=[t["entity"] for t in tickets])

    modele = make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4)),  # morceaux de 2 à 4 lettres
        LogisticRegression(max_iter=1000),
    )
    modele.fit([preparer_texte(textes[i]) for i in i_train], [tickets[i]["entity"] for i in i_train])

    test = [tickets[i] for i in i_test]
    avec_regles = [extraire(textes[i], modele=None) for i in i_test]
    avec_modele = [extraire(textes[i], modele=modele) for i in i_test]

    lignes = ["# Évaluation sur le jeu de test", "",
              f"{len(i_train)} tickets d'entraînement, {len(i_test)} tickets de test jamais vus.", "",
              "| Enseigne | n | Enseigne (règles) | Enseigne (modèle) | Date (règle) | Total (règle) |",
              "|---|---:|---:|---:|---:|---:|"]
    for enseigne in ["CARREFOUR", "LIDL", "INTERMARCHE", None]:
        regles, n = exactitude(avec_regles, test, "entity", enseigne)
        ia, _ = exactitude(avec_modele, test, "entity", enseigne)
        jour, _ = exactitude(avec_modele, test, "date", enseigne)
        total, _ = exactitude(avec_modele, test, "total_amount", enseigne)
        nom = enseigne or "**Tous**"
        lignes.append(f"| {nom} | {n} | {regles:.0%} | {ia:.0%} | {jour:.0%} | {total:.0%} |")

    Path("models").mkdir(exist_ok=True)
    joblib.dump(modele, "models/modele_enseigne.joblib")
    Path("reports").mkdir(exist_ok=True)
    Path("reports/evaluation.md").write_text("\n".join(lignes) + "\n")
    print("\n".join(lignes))
    print("\nModèle sauvegardé : models/modele_enseigne.joblib")
