"""Modèle d'extraction entraîné (approche hybride, cahier des charges §4.4 et §8.4).

Ce qui est **appris** et ce qui reste **déterministe** :

| Champ   | Génération des candidats        | Choix final                                   |
|---------|---------------------------------|-----------------------------------------------|
| entité  | — (texte OCR complet)           | **appris** : TF-IDF caractères + régression logistique |
| total   | règles (regex des montants)     | **appris** : classifieur de candidats, qui reçoit aussi l'avis de la baseline comme indice |
| date    | règles (regex des dates)        | **appris** : classifieur de candidats         |

Les règles ne servent qu'à **lister** les possibilités ; c'est le modèle qui
décide lequel est le bon, à partir du contexte (mots de la ligne et des
lignes voisines, position, fréquence de la valeur…). Si aucun candidat
n'existe, ou si le modèle d'enseigne est incertain (probabilité < 0,55),
l'extracteur retombe sur les règles et l'indique (``methode``).

Le texte est « anonymisé » avant vectorisation de l'enseigne (chiffres
remplacés par 0) : le modèle ne peut pas mémoriser un numéro de carte de
fidélité ou un montant particulier.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline

from docflow.extraction import regles
from docflow.extraction.candidats import CandidatDate, CandidatMontant, Ligne
from docflow.extraction.normalisation import INCONNUE

SEUIL_ENTITE = 0.55

MOTS_MONTANT = (
    "TOTAL", "PAYER", "MONTANT", " DU", "NET", "TTC", "CB", "CARTE", "BANCAIRE", "EUR", "€",
    "TVA", " HT", "SOUS", "ELIGIBLE", "REMISE", "REDUCTION", "RENDU", "RENDRE", "ESPECES",
    "PROMOTION", "ECONOMI", "RETOUR", "CREDIT", "DEBIT", " X ", "%", "SOLDE", "FIDELITE",
    "ARTICLE", "PAYE",
)
MOTS_DATE = ("DATE", "LE ", " A ", "CB", "CARTE", "TICKET", "CAISSE", "RETOUR", "SIGNATURE", "VALID")


def texte_anonymise(lignes: list[Ligne]) -> str:
    """Texte normalisé où chaque chiffre devient ``0``.

    Exemple :
        >>> texte_anonymise([Ligne("Carte 9135 7200", "CARTE 9135 7200", 1, 0, 0.1)])
        'CARTE 0000 0000'
    """
    return "\n".join(re.sub(r"\d", "0", ligne.norm) for ligne in lignes)


def _mots(prefixe: str, texte: str, mots: tuple[str, ...]) -> dict[str, float]:
    texte = f" {texte} "
    return {f"{prefixe}{m.strip() or m}": 1.0 for m in mots if m in texte}


def caracteristiques_montants(candidats: list[CandidatMontant]) -> list[dict[str, float]]:
    """Décrit chaque montant candidat par son contexte (une ligne = un dict)."""
    if not candidats:
        return []
    positifs = sorted({c.valeur for c in candidats if c.valeur > 0}, reverse=True)
    rang = {v: i for i, v in enumerate(positifs)}
    frequence = Counter(c.valeur for c in candidats)
    nb_lignes = max(c.ligne.index for c in candidats) + 1
    choix_regles = regles.total_par_regles(candidats)
    resultat = []
    for c in candidats:
        f: dict[str, float] = {
            "y_doc": c.ligne.y_doc,
            "index_rel": c.ligne.index / nb_lignes,
            "dernier_de_ligne": float(c.rang_dans_ligne == c.nb_dans_ligne - 1),
            "nb_dans_ligne": float(c.nb_dans_ligne),
            "negatif": float(c.valeur <= 0),
            "log_valeur": math.log1p(abs(float(c.valeur))),
            "est_max": float(bool(positifs) and c.valeur == positifs[0]),
            "rang_valeur": rang.get(c.valeur, len(positifs)) / max(len(positifs), 1),
            "frequence": float(frequence[c.valeur]),
            "frequence_2_plus": float(frequence[c.valeur] >= 2),
            "page": float(c.ligne.page),
            # Signaux de la baseline, utilisés comme indices (approche hybride) :
            "choix_regles": float(c is choix_regles),
            "valeur_choix_regles": float(choix_regles is not None and c.valeur == choix_regles.valeur),
            "piege": float(any(p in c.ligne.norm for p in regles.LIBELLES_PIEGES)),
        }
        for priorite, libelle in enumerate(regles.LIBELLES_TOTAL):
            if libelle in c.ligne.norm:
                f[f"libelle_{libelle}"] = 1.0
                f.setdefault("priorite_libelle", 1.0 - priorite / len(regles.LIBELLES_TOTAL))
        f.update(_mots("l_", c.ligne.norm, MOTS_MONTANT))
        f.update(_mots("p_", c.precedente, MOTS_MONTANT))
        f.update(_mots("s_", c.suivante, MOTS_MONTANT))
        resultat.append(f)
    return resultat


def caracteristiques_dates(candidats: list[CandidatDate]) -> list[dict[str, float]]:
    """Décrit chaque date candidate par son contexte."""
    if not candidats:
        return []
    valeurs = sorted({c.valeur for c in candidats})
    frequence = Counter(c.valeur for c in candidats)
    resultat = []
    for i, c in enumerate(candidats):
        f: dict[str, float] = {
            "y_doc": c.ligne.y_doc,
            "heure": float(c.heure_sur_ligne),
            "annee_4": float(c.annee_4_chiffres),
            "frequence": float(frequence[c.valeur]),
            "premiere": float(i == 0),
            "derniere": float(i == len(candidats) - 1),
            "plus_recente": float(c.valeur == valeurs[-1]),
            "plus_ancienne": float(c.valeur == valeurs[0]),
            "nb_dates_distinctes": float(len(valeurs)),
        }
        f.update(_mots("l_", c.ligne.norm, MOTS_DATE))
        resultat.append(f)
    return resultat


def nouveau_classifieur_candidats(c: float = 1.0) -> Pipeline:
    """Régression logistique sur caractéristiques creuses : simple et interprétable."""
    return make_pipeline(
        DictVectorizer(sparse=True),
        LogisticRegression(C=c, class_weight="balanced", max_iter=5000),
    )


def nouveau_classifieur_entite(c: float = 3.0) -> Pipeline:
    return make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=2, sublinear_tf=True),
        LogisticRegression(C=c, class_weight="balanced", max_iter=5000),
    )


@dataclass
class ModeleExtraction:
    """Les trois classifieurs + leurs métadonnées (artefact versionné)."""

    entite: Pipeline
    total: Pipeline
    date: Pipeline
    version: str
    metadonnees: dict[str, Any] = field(default_factory=dict)

    # ---------------------------------------------------------- prédiction
    def predire_entite(self, lignes: list[Ligne]) -> tuple[str, float]:
        if not lignes:
            return INCONNUE, 0.0
        probas = self.entite.predict_proba([texte_anonymise(lignes)])[0]
        meilleure = int(np.argmax(probas))
        if probas[meilleure] < SEUIL_ENTITE:
            return INCONNUE, float(probas[meilleure])
        return str(self.entite.classes_[meilleure]), float(probas[meilleure])

    @staticmethod
    def _choisir(pipeline: Pipeline, candidats: list, caracteristiques: list[dict]):
        if not candidats:
            return None, 0.0
        probas = pipeline.predict_proba(caracteristiques)[:, list(pipeline.classes_).index(1)]
        i = int(np.argmax(probas))
        return candidats[i], float(probas[i])

    def choisir_total(self, candidats: list[CandidatMontant]) -> tuple[CandidatMontant | None, float]:
        positifs = [c for c in candidats if c.valeur > 0]
        # Les caractéristiques sont calculées sur TOUS les candidats (contexte),
        # mais seul un montant positif peut être choisi comme total.
        feats = caracteristiques_montants(candidats)
        garder = [i for i, c in enumerate(candidats) if c.valeur > 0]
        return self._choisir(self.total, positifs, [feats[i] for i in garder])

    def choisir_date(self, candidats: list[CandidatDate]) -> tuple[CandidatDate | None, float]:
        return self._choisir(self.date, candidats, caracteristiques_dates(candidats))

    # ---------------------------------------------------------- persistance
    def sauvegarder(self, chemin: Path) -> None:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, chemin)

    @classmethod
    def charger(cls, chemin: Path) -> ModeleExtraction:
        modele = joblib.load(chemin)
        if not isinstance(modele, cls):
            raise TypeError(f"{chemin} n'est pas un modèle DocFlow")
        return modele
