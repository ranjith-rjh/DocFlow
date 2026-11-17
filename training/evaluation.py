"""Évaluation de l'extraction face aux annotations humaines (§11.1).

Usage :
    python -m training.evaluation --partitions train,validation   # mise au point
    python -m training.evaluation --partitions test --final       # bilan, une seule fois

Le rapport versionné (``reports/*.md``) ne contient que des **agrégats** et des
types d'erreurs : jamais de texte de ticket ni de nom de fichier (les noms
contiennent la date et le montant). Le détail par fichier part dans
``reports/raw/`` (ignoré par Git).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np

from docflow.extraction.extracteur import Selecteur, extraire
from training.corpus import charger_annotations
from training.ocr_corpus import DOSSIER_OCR, DOSSIER_REFERENCE

DOSSIER_RAPPORTS = Path("reports")
CHAMPS = ("entity", "date", "total_amount")


def charger_pages(fichier: str) -> list[dict]:
    """Pages OCR mises en cache par ``training.ocr_corpus``."""
    chemin = DOSSIER_OCR / (Path(fichier).stem + ".json")
    return json.loads(chemin.read_text(encoding="utf-8"))["pages"]


# ---------------------------------------------------------------- CER / WER
def distance_edition(a: list | str, b: list | str) -> int:
    """Distance de Levenshtein, vectorisée ligne par ligne avec numpy.

    Exemple :
        >>> distance_edition("TOTAL", "T0TAL"), distance_edition("abc", "")
        (1, 3)
    """
    if not a or not b:
        return max(len(a), len(b))
    codes = {s: i for i, s in enumerate(set(a) | set(b))}
    va = np.array([codes[s] for s in a])
    vb = np.array([codes[s] for s in b])
    indices = np.arange(len(vb) + 1)
    precedente = indices.copy()
    for i in range(1, len(va) + 1):
        candidat = np.empty_like(precedente)
        candidat[0] = i
        # substitution (ou égalité) et suppression
        candidat[1:] = np.minimum(precedente[:-1] + (vb != va[i - 1]), precedente[1:] + 1)
        # insertion : courant[j] = min(candidat[j], courant[j-1] + 1)
        precedente = np.minimum.accumulate(candidat - indices) + indices
    return int(precedente[-1])


def _normaliser_texte(texte: str) -> str:
    return re.sub(r"\s+", " ", texte).strip()


def cer_wer(reference: str, hypothese: str) -> tuple[float, float]:
    """Taux d'erreur caractères et mots (0 = parfait).

    Exemple :
        >>> cer_wer("TOTAL 6.43", "TOTAL 6.48")
        (0.1, 0.5)
    """
    ref, hyp = _normaliser_texte(reference), _normaliser_texte(hypothese)
    cer = distance_edition(ref, hyp) / max(len(ref), 1)
    wer = distance_edition(ref.split(), hyp.split()) / max(len(ref.split()), 1)
    return round(cer, 4), round(wer, 4)


# ---------------------------------------------------------------- Extraction
@dataclass
class Ligne:
    fichier: str
    entite_ref: str
    partition: str
    correct: dict[str, bool]
    predit: dict[str, str | None]
    attendu: dict[str, str]
    methode: dict[str, str]


def evaluer(partitions: set[str], selecteur: Selecteur | None) -> list[Ligne]:
    """Extrait chaque ticket des partitions demandées et compare à la référence."""
    resultats = []
    for a in charger_annotations():
        if a["partition"] not in partitions:
            continue
        r = extraire(charger_pages(a["fichier"]), selecteur, aujourd_hui=date(2026, 11, 16))
        predit = r.en_dict()
        attendu = {"entity": a["entity"], "date": a["date"], "total_amount": a["total_amount"]}
        resultats.append(Ligne(
            fichier=a["fichier"],
            entite_ref=a["entity"],
            partition=a["partition"],
            correct={c: predit[c] == attendu[c] for c in CHAMPS},
            predit={c: predit[c] for c in CHAMPS},
            attendu=attendu,
            methode=r.methode,
        ))
    return resultats


def type_erreur(ligne: Ligne, champ: str) -> str:
    """Catégorise une erreur sans révéler de valeur."""
    if ligne.predit[champ] in (None, "UNKNOWN"):
        return "valeur absente"
    if champ == "entity":
        return "mauvaise enseigne"
    if champ == "date":
        return "autre date du ticket"
    try:
        ecart = float(ligne.predit[champ]) - float(ligne.attendu[champ])
    except (TypeError, ValueError):
        return "montant illisible"
    if ecart > 0:
        return "montant trop élevé"
    return "montant inférieur (article, sous-total, TVA…)"


def tableau_exactitude(resultats: list[Ligne]) -> str:
    """Tableau Markdown : exactitude par champ, globale et par enseigne."""
    groupes: dict[str, list[Ligne]] = defaultdict(list)
    for r in resultats:
        groupes[r.entite_ref].append(r)
    groupes["GLOBAL"] = resultats
    lignes = ["| Enseigne | n | Entité | Date | Total | Document entièrement correct |",
              "|---|---:|---:|---:|---:|---:|"]
    for nom in sorted(groupes, key=lambda g: (g == "GLOBAL", g)):
        rs = groupes[nom]
        n = len(rs)
        taux = [sum(r.correct[c] for r in rs) / n for c in CHAMPS]
        complet = sum(all(r.correct.values()) for r in rs) / n
        cellules = " | ".join(f"{t:.1%}" for t in (*taux, complet))
        gras = "**" if nom == "GLOBAL" else ""
        lignes.append(f"| {gras}{nom}{gras} | {n} | {cellules} |")
    return "\n".join(lignes)


def precision_rappel_entite(resultats: list[Ligne]) -> str:
    """Précision / rappel / F1 de la classification d'enseigne."""
    lignes = ["| Enseigne | Précision | Rappel | F1 |", "|---|---:|---:|---:|"]
    for e in sorted({r.entite_ref for r in resultats}):
        vp = sum(r.predit["entity"] == e and r.entite_ref == e for r in resultats)
        predits = sum(r.predit["entity"] == e for r in resultats)
        reels = sum(r.entite_ref == e for r in resultats)
        p = vp / predits if predits else 0.0
        rap = vp / reels if reels else 0.0
        f1 = 2 * p * rap / (p + rap) if p + rap else 0.0
        lignes.append(f"| {e} | {p:.1%} | {rap:.1%} | {f1:.1%} |")
    return "\n".join(lignes)


def tableau_erreurs(resultats: list[Ligne]) -> str:
    compte: dict[tuple[str, str, str], int] = defaultdict(int)
    for r in resultats:
        for c in CHAMPS:
            if not r.correct[c]:
                compte[(r.entite_ref, c, type_erreur(r, c))] += 1
    if not compte:
        return "_Aucune erreur._"
    lignes = ["| Enseigne | Champ | Type d'erreur | Nombre |", "|---|---|---|---:|"]
    for (e, c, t), n in sorted(compte.items()):
        lignes.append(f"| {e} | {c} | {t} | {n} |")
    return "\n".join(lignes)


def tableau_ocr(fichiers: list[tuple[str, str]]) -> str:
    """CER/WER moyens des PDF (couche texte prise comme référence)."""
    par_entite: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for fichier, entite in fichiers:
        ref = DOSSIER_REFERENCE / (Path(fichier).stem + ".txt")
        if not ref.exists():
            continue
        hyp = "\n".join(p["texte"] for p in charger_pages(fichier))
        par_entite[entite].append(cer_wer(ref.read_text(encoding="utf-8"), hyp))
    if not par_entite:
        return "_Pas de référence texte (aucun PDF)._"
    lignes = ["| Enseigne | n | CER moyen | WER moyen |", "|---|---:|---:|---:|"]
    for e, valeurs in sorted(par_entite.items()):
        cer = sum(v[0] for v in valeurs) / len(valeurs)
        wer = sum(v[1] for v in valeurs) / len(valeurs)
        lignes.append(f"| {e} | {len(valeurs)} | {cer:.1%} | {wer:.1%} |")
    return "\n".join(lignes)


def ecrire_detail(resultats: list[Ligne], nom: str) -> None:
    """Détail par fichier, privé (reports/raw/ est ignoré par Git)."""
    dossier = DOSSIER_RAPPORTS / "raw"
    dossier.mkdir(parents=True, exist_ok=True)
    with open(dossier / f"{nom}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fichier", "partition", *[f"{c}_{s}" for c in CHAMPS for s in ("attendu", "predit")]])
        for r in resultats:
            w.writerow([r.fichier, r.partition,
                        *[v for c in CHAMPS for v in (r.attendu[c], r.predit[c])]])


def rapport(resultats: list[Ligne], titre: str, avec_ocr: bool = True) -> str:
    """Assemble un rapport Markdown agrégé."""
    blocs = [
        f"## {titre}",
        "### Exactitude",
        tableau_exactitude(resultats),
        "### Enseigne : précision, rappel, F1",
        precision_rappel_entite(resultats),
        "### Types d'erreurs",
        tableau_erreurs(resultats),
    ]
    if avec_ocr:
        blocs += ["### Qualité OCR (PDF, couche texte comme référence)",
                  "Approximation : l'ordre de lecture de la couche texte peut différer de "
                  "celui de l'OCR, ce qui augmente artificiellement le CER.",
                  tableau_ocr([(r.fichier, r.entite_ref) for r in resultats])]
    return "\n\n".join(blocs)


RAPPORT_FINAL = DOSSIER_RAPPORTS / "evaluation_finale.md"


RAPPORT_CORRIGE = DOSSIER_RAPPORTS / "evaluation_finale_corrigee.md"


def evaluation_finale(chemin_modele: Path, correctif: str | None = None) -> None:
    """Bilan sur le jeu de test : baseline et modèle figés, **une seule fois**.

    Le script refuse de s'exécuter si le rapport final existe déjà : on ne
    retouche ni le modèle ni le test après avoir vu ses résultats (§8.3).
    """
    from docflow.extraction.modele import ModeleExtraction

    sortie = RAPPORT_FINAL
    if correctif:
        # Réévaluation exceptionnelle, documentée : le rapport d'origine est
        # conservé, le modèle n'est pas modifié, la raison est écrite.
        if not RAPPORT_FINAL.exists() or RAPPORT_CORRIGE.exists():
            raise SystemExit("Correctif impossible : rapport d'origine absent ou correctif déjà fait.")
        sortie = RAPPORT_CORRIGE
    elif RAPPORT_FINAL.exists():
        raise SystemExit(f"{RAPPORT_FINAL} existe déjà : le test final ne se rejoue pas.")
    modele = ModeleExtraction.charger(chemin_modele)
    baseline = evaluer({"test"}, selecteur=None)
    entraine = evaluer({"test"}, selecteur=modele)
    ecrire_detail(baseline, "test_baseline")
    ecrire_detail(entraine, "test_modele")

    def ligne(nom: str, rs: list[Ligne]) -> str:
        taux = [sum(r.correct[c] for r in rs) / len(rs) for c in CHAMPS]
        complet = sum(all(r.correct.values()) for r in rs) / len(rs)
        return f"| {nom} | " + " | ".join(f"{t:.1%}" for t in (*taux, complet)) + " |"

    methodes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in entraine:
        for champ, m in r.methode.items():
            methodes[champ][m] += 1
    texte_methodes = "\n".join(
        f"| {c} | " + ", ".join(f"{m} : {n}" for m, n in sorted(v.items())) + " |"
        for c, v in sorted(methodes.items()))

    titre = "Évaluation finale corrigée" if correctif else "Évaluation finale"
    entete_correctif = f"\n> **Réévaluation corrective.** Raison : {correctif}\n" if correctif else ""
    contenu = f"""# {titre} — jeu de test indépendant
{entete_correctif}
> Exécutée une seule fois, le {datetime.now(UTC).date().isoformat()}, avec le modèle
> `{modele.version}` et la baseline figés. {len(entraine)} fichiers jamais vus
> pendant l'entraînement ni la mise au point (12 Carrefour, 6 Lidl, 3 Intermarché).

## Synthèse : baseline contre modèle, même jeu de test

| Méthode | Entité | Date | Total | Document entièrement correct |
|---|---:|---:|---:|---:|
{ligne("Baseline par règles", baseline)}
{ligne("Modèle hybride entraîné", entraine)}

**Lecture prudente :** avec 21 documents, une erreur vaut 4,8 points au global
et 33 points pour Intermarché (3 documents). Ces chiffres montrent une
tendance, pas une performance garantie.

## Méthode réellement utilisée par champ (modèle hybride)

| Champ | Nombre de documents |
|---|---|
{texte_methodes}

{rapport(baseline, "Détail — baseline par règles", avec_ocr=False)}

{rapport(entraine, "Détail — modèle hybride entraîné", avec_ocr=True)}
"""
    sortie.write_text(contenu, encoding="utf-8")
    print(contenu)


def main() -> None:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--partitions", default="train,validation")
    parseur.add_argument("--sortie", default="reports/baseline_dev.md")
    parseur.add_argument("--final", action="store_true", help="bilan unique sur le jeu de test")
    parseur.add_argument("--modele", type=Path, default=Path("models/docflow-extraction.joblib"))
    parseur.add_argument("--correctif", help="raison d'une réévaluation corrective (une seule)")
    args = parseur.parse_args()
    if args.final:
        evaluation_finale(args.modele, args.correctif)
        return
    partitions = set(args.partitions.split(","))
    if "test" in partitions:
        raise SystemExit("Le jeu de test ne s'évalue qu'avec --final (une seule fois).")
    resultats = evaluer(partitions, selecteur=None)
    ecrire_detail(resultats, Path(args.sortie).stem)
    texte = rapport(resultats, f"Baseline par règles — partitions {sorted(partitions)}")
    Path(args.sortie).parent.mkdir(parents=True, exist_ok=True)
    Path(args.sortie).write_text(f"# Évaluation\n\n{texte}\n", encoding="utf-8")
    print(texte)


if __name__ == "__main__":
    main()
