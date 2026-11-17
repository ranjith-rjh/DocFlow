"""Entraînement du modèle d'extraction (tickets DF-20 à DF-23).

Protocole (cahier des charges §8.3 et §8.4) :
    1. On n'utilise QUE les partitions ``train`` et ``validation`` (116 fichiers) ;
       le jeu ``test`` n'est jamais lu ici.
    2. Le corpus étant petit (Intermarché : 13 fichiers hors test), la mise au
       point se fait par **validation croisée groupée et stratifiée** (5 plis,
       un ticket physique jamais coupé entre deux plis) sur train + validation.
    3. Pour chaque champ, on compare la baseline par règles et le modèle sur
       les mêmes plis, et on choisit l'hyperparamètre ``C`` par champ.
    4. Le modèle final est réentraîné sur train + validation et sauvegardé avec
       sa fiche (version, données, métriques de validation croisée).

Usage :
    docker compose run --rm outils python -m training.entrainement
"""

from __future__ import annotations

import json
import platform
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import sklearn
from sklearn.model_selection import StratifiedGroupKFold

from docflow.extraction import regles
from docflow.extraction.candidats import aplatir, candidats_dates, candidats_montants
from docflow.extraction.modele import (
    ModeleExtraction,
    caracteristiques_dates,
    caracteristiques_montants,
    nouveau_classifieur_candidats,
    nouveau_classifieur_entite,
    texte_anonymise,
)
from training.corpus import charger_annotations
from training.evaluation import charger_pages

VERSION = "docflow-extraction-1.0.0"
CHEMIN_MODELE = Path("models/docflow-extraction.joblib")
CHEMIN_FICHE = Path("models/docflow-extraction.json")
FICHE_DOCS = Path("docs/modele.md")
GRILLE_C = (0.1, 0.3, 1.0, 3.0, 10.0)
AUJOURDHUI = date(2026, 11, 16)
NB_PLIS = 5


class Document:
    """Un ticket prêt pour l'apprentissage : texte, candidats, vérité."""

    def __init__(self, annotation: dict) -> None:
        self.groupe = annotation["groupe"]
        self.entite = annotation["entity"]
        self.date = annotation["date"]
        self.total = annotation["total_amount"]
        self.lignes = aplatir(charger_pages(annotation["fichier"]))
        self.montants = candidats_montants(self.lignes)
        self.dates = candidats_dates(self.lignes, AUJOURDHUI)


def _exemples_montants(docs: list[Document]):
    x, y = [], []
    for d in docs:
        feats = caracteristiques_montants(d.montants)
        for c, f in zip(d.montants, feats, strict=True):
            if c.valeur > 0:
                x.append(f)
                y.append(int(str(c.valeur) == d.total))
    return x, y


def _exemples_dates(docs: list[Document]):
    x, y = [], []
    for d in docs:
        for c, f in zip(d.dates, caracteristiques_dates(d.dates), strict=True):
            x.append(f)
            y.append(int(c.valeur.isoformat() == d.date))
    return x, y


def _entrainer(docs: list[Document], c_entite: float, c_total: float, c_date: float,
               meta: dict | None = None) -> ModeleExtraction:
    entite = nouveau_classifieur_entite(c_entite).fit(
        [texte_anonymise(d.lignes) for d in docs], [d.entite for d in docs])
    total = nouveau_classifieur_candidats(c_total).fit(*_exemples_montants(docs))
    jour = nouveau_classifieur_candidats(c_date).fit(*_exemples_dates(docs))
    return ModeleExtraction(entite, total, jour, VERSION, meta or {})


def _scores(docs: list[Document], modele: ModeleExtraction | None) -> dict[str, list[bool]]:
    """Exactitude par document : modèle si fourni, sinon baseline par règles."""
    res: dict[str, list[bool]] = defaultdict(list)
    for d in docs:
        if modele is None:
            entite, _ = regles.entite_par_mots_cles(d.lignes)
            total = regles.total_par_regles(d.montants)
            jour = regles.date_par_regles(d.dates)
        else:
            entite, _ = modele.predire_entite(d.lignes)
            total, _ = modele.choisir_total(d.montants)
            jour, _ = modele.choisir_date(d.dates)
        res["entity"].append(entite == d.entite)
        res["total_amount"].append(total is not None and str(total.valeur) == d.total)
        res["date"].append(jour is not None and jour.valeur.isoformat() == d.date)
    return res


def validation_croisee(docs: list[Document], c: float) -> dict[str, float]:
    """Exactitude moyenne par champ (modèle entraîné avec ``C = c`` partout)."""
    plis = StratifiedGroupKFold(n_splits=NB_PLIS, shuffle=True, random_state=42)
    etiquettes = [d.entite for d in docs]
    groupes = [d.groupe for d in docs]
    cumul: dict[str, list[bool]] = defaultdict(list)
    for app, val in plis.split(np.zeros(len(docs)), etiquettes, groupes):
        modele = _entrainer([docs[i] for i in app], c, c, c)
        for champ, v in _scores([docs[i] for i in val], modele).items():
            cumul[champ].extend(v)
    return {champ: float(np.mean(v)) for champ, v in cumul.items()}


def main() -> None:
    annotations = [a for a in charger_annotations() if a["partition"] in ("train", "validation")]
    docs = [Document(a) for a in annotations]
    print(f"{len(docs)} documents (train + validation), {NB_PLIS} plis groupés")

    baseline = {k: float(np.mean(v)) for k, v in _scores(docs, None).items()}
    print(f"Baseline règles (sans apprentissage) : {baseline}")

    resultats = {}
    for c in GRILLE_C:
        resultats[c] = validation_croisee(docs, c)
        print(f"  C={c:<5} {resultats[c]}")
    meilleurs = {champ: max(GRILLE_C, key=lambda c, ch=champ: resultats[c][ch])
                 for champ in ("entity", "total_amount", "date")}
    cv_meilleurs = {champ: resultats[meilleurs[champ]][champ] for champ in meilleurs}
    print(f"C retenus : {meilleurs} -> exactitude CV {cv_meilleurs}")

    meta = {
        "version": VERSION,
        "entraine_le": datetime.now(UTC).isoformat(timespec="seconds"),
        "donnees": {"partitions": ["train", "validation"], "documents": len(docs),
                    "par_enseigne": {e: sum(d.entite == e for d in docs)
                                     for e in sorted({d.entite for d in docs})}},
        "hyperparametres": {"C": meilleurs, "seuil_entite": 0.55},
        "validation_croisee": {"plis": NB_PLIS, "baseline_regles": baseline,
                               "modele": cv_meilleurs},
        "environnement": {"python": platform.python_version(), "scikit_learn": sklearn.__version__},
    }
    modele = _entrainer(docs, meilleurs["entity"], meilleurs["total_amount"], meilleurs["date"], meta)
    modele.sauvegarder(CHEMIN_MODELE)
    CHEMIN_FICHE.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    ecrire_fiche_docs(meta, resultats)
    print(f"Modèle sauvegardé : {CHEMIN_MODELE}")


def ecrire_fiche_docs(meta: dict, resultats: dict) -> None:
    """Fiche du modèle versionnée dans docs/ (agrégats uniquement)."""
    b, m = meta["validation_croisee"]["baseline_regles"], meta["validation_croisee"]["modele"]
    lignes_grille = "\n".join(
        f"| {c} | {r['entity']:.1%} | {r['date']:.1%} | {r['total_amount']:.1%} |"
        for c, r in resultats.items())
    FICHE_DOCS.write_text(f"""# Fiche du modèle `{meta['version']}`

> Générée par `python -m training.entrainement` le {meta['entraine_le']}.
> L'artefact (`models/docflow-extraction.joblib`) n'est pas versionné dans Git :
> il est construit à partir des tickets privés.

## Ce qui est appris (§8.4)

| Champ | Candidats | Choix | Statut |
|---|---|---|---|
| Enseigne | texte OCR complet, chiffres masqués | TF-IDF n-grammes de caractères (2–4) + régression logistique ; `UNKNOWN` si probabilité < 0,55 | **appris** |
| Total | règles : tous les montants à 2 décimales | régression logistique sur le contexte de chaque montant (mots de la ligne et des voisines, position, rang, fréquence) | **hybride** (candidats par règles, choix appris) |
| Date | règles : toutes les dates plausibles | régression logistique sur le contexte (heure sur la ligne, fréquence, position, mots-clés) | **hybride** (candidats par règles, choix appris) |

Si un champ n'a aucun candidat, ou si le modèle d'enseigne est incertain
(mise en page jamais vue), l'extracteur retombe sur la baseline et le signale
(`methode = regles` ou `aucun`) ; aucune valeur n'est inventée.

## Données

{meta['donnees']['documents']} documents (partitions *train* + *validation*) :
{", ".join(f"{e} {n}" for e, n in meta['donnees']['par_enseigne'].items())}.
Le jeu de test (21 fichiers) n'a jamais été utilisé pour l'entraînement ni pour
le choix des hyperparamètres.

## Validation croisée groupée ({meta['validation_croisee']['plis']} plis, train + validation)

| C | Enseigne | Date | Total |
|---|---:|---:|---:|
{lignes_grille}

**Retenu par champ** : {meta['hyperparametres']['C']}

| Méthode | Enseigne | Date | Total |
|---|---:|---:|---:|
| Baseline règles (sans apprentissage) | {b['entity']:.1%} | {b['date']:.1%} | {b['total_amount']:.1%} |
| Modèle (validation croisée) | {m['entity']:.1%} | {m['date']:.1%} | {m['total_amount']:.1%} |

La baseline n'apprend rien : son score sur train + validation est directement
comparable. Le résultat final, sur le test indépendant, est dans
`reports/evaluation_finale.md`.

## Environnement

Python {meta['environnement']['python']}, scikit-learn {meta['environnement']['scikit_learn']}
(version figée dans `pyproject.toml` pour charger l'artefact à l'identique sur Fedora).
""", encoding="utf-8")


if __name__ == "__main__":
    main()
