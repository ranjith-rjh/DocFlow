"""Baseline par règles et mots-clés (cahier des charges §4.4, §8.4 étape 1).

Point de comparaison volontairement simple et lisible : ce n'est **pas** de
l'IA. Le modèle entraîné (``modele.py``) devra faire mieux sur le même jeu de
test pour justifier sa présence.
"""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher

from docflow.extraction.candidats import CandidatDate, CandidatMontant, Ligne
from docflow.extraction.normalisation import INCONNUE

MOTS_ENSEIGNES = {
    "CARREFOUR": ("CARREFOUR",),
    "LIDL": ("LIDL",),
    "INTERMARCHE": ("INTERMARCHE", "MOUSQUETAIRES"),
}

# Libellés du total, du plus fiable au moins fiable.
LIBELLES_TOTAL = (
    "TOTAL A PAYER",
    "NET A PAYER",
    "MONTANT DU",
    "A PAYER",
    "TOTAL TTC",
    "TOTAL",
)
# Lignes qui contiennent « TOTAL » sans être le total payé.
LIBELLES_PIEGES = ("SOUS-TOTAL", "SOUS TOTAL", "ELIGIBLE", "TOTAL TVA", "TOTAL HT",
                   "PROMOTION", "ECONOMIS", "REMISE")


def _ressemble(mot: str, cle: str) -> bool:
    """Tolère les petites erreurs OCR (« CARREF0UR », « LlDL »)."""
    if cle in mot:
        return True
    return len(mot) >= 4 and SequenceMatcher(None, mot, cle).ratio() >= 0.8


def entite_par_mots_cles(lignes: list[Ligne]) -> tuple[str, float]:
    """Compte les mentions de chaque enseigne ; ``UNKNOWN`` si aucune ou égalité.

    Retourne ``(enseigne, confiance)`` où la confiance est la part des mentions
    de l'enseigne gagnante.
    """
    scores: Counter = Counter()
    for ligne in lignes:
        for mot in ligne.norm.replace(".", " ").split():
            for entite, cles in MOTS_ENSEIGNES.items():
                if any(_ressemble(mot, c) for c in cles):
                    scores[entite] += 1
    if not scores:
        return INCONNUE, 0.0
    (premiere, n1), *reste = scores.most_common()
    if reste and reste[0][1] == n1:
        return INCONNUE, 0.0
    return premiere, round(n1 / sum(scores.values()), 3)


def total_par_regles(candidats: list[CandidatMontant]) -> CandidatMontant | None:
    """Choisit le montant du premier libellé de total trouvé, par priorité.

    Sur la ligne retenue, on prend le dernier montant (colonne de droite).
    À défaut de libellé, on prend le plus grand montant positif.
    """
    positifs = [c for c in candidats if c.valeur > 0]
    for libelle in LIBELLES_TOTAL:
        for c in positifs:
            texte = c.ligne.norm
            if libelle in texte and not any(p in texte for p in LIBELLES_PIEGES):
                if c.rang_dans_ligne == c.nb_dans_ligne - 1:
                    return c
    return max(positifs, key=lambda c: c.valeur, default=None)


def date_par_regles(candidats: list[CandidatDate]) -> CandidatDate | None:
    """Préfère une date accompagnée d'une heure (date de passage en caisse),
    sinon la date la plus fréquente, sinon la première."""
    if not candidats:
        return None
    avec_heure = [c for c in candidats if c.heure_sur_ligne]
    if avec_heure:
        return avec_heure[0]
    plus_frequente, _ = Counter(c.valeur for c in candidats).most_common(1)[0]
    return next(c for c in candidats if c.valeur == plus_frequente)
