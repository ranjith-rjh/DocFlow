"""Vérité de référence et découpage du corpus (tickets DF-02 et DF-03).

Les annotations sont déduites des noms de fichiers saisis à la main
(décision D-04) :

    <entite>_<AAAA>-<JJ>-<MM>_<montant>[_<vue>].<ext>
    carrefour_2025-17-04_12.34.pdf -> CARREFOUR, 2025-04-17, 12.34 EUR

Le découpage entraînement / validation / test est :
    * stratifié par enseigne (chaque enseigne présente dans chaque groupe) ;
    * groupé par ticket physique (toutes les vues d'un ticket ensemble) ;
    * déterministe (graine fixe) et figé dans ``data/annotations/split.csv``.

Usage :
    python -m training.corpus            # génère annotations.csv et split.csv
"""

from __future__ import annotations

import csv
import math
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

RACINE_DONNEES = Path("data")
DOSSIER_BRUT = RACINE_DONNEES / "raw"
FICHIER_ANNOTATIONS = RACINE_DONNEES / "annotations" / "annotations.csv"
FICHIER_SPLIT = RACINE_DONNEES / "annotations" / "split.csv"
GRAINE = 42
PART_VALIDATION = 0.15
PART_TEST = 0.15

MOTIF_NOM = re.compile(
    r"^(?P<entite>carrefour|lidl|intermarche)_"
    r"(?P<annee>\d{4})-(?P<jour>\d{2})-(?P<mois>\d{2})_"
    r"(?P<montant>\d+\.\d{2})(?:_(?P<vue>[a-z]))?\.(?P<ext>pdf|png|jpe?g)$"
)


class NomInvalide(ValueError):
    """Nom de fichier qui ne respecte pas la convention de nommage."""


@dataclass(frozen=True)
class Annotation:
    """Vérité de référence d'un fichier du corpus."""

    fichier: str  # chemin relatif à data/raw, ex. "lidl/lidl_2023-01-09_10.00.png"
    entity: str
    date: date
    total_amount: Decimal
    currency: str
    groupe: str  # identifiant du ticket physique


def lire_nom(nom: str) -> tuple[str, date, Decimal, str | None]:
    """Décode un nom de fichier du corpus.

    Exemple :
        >>> lire_nom("carrefour_2025-17-04_12.34.pdf")
        ('CARREFOUR', datetime.date(2025, 4, 17), Decimal('12.34'), None)
        >>> lire_nom("lidl_2024-03-05_10.00_b.png")[3]
        'b'
    """
    m = MOTIF_NOM.match(nom)
    if not m:
        raise NomInvalide(nom)
    try:
        jour = date(int(m["annee"]), int(m["mois"]), int(m["jour"]))
    except ValueError as exc:
        raise NomInvalide(f"{nom} : date impossible ({exc})") from exc
    return m["entite"].upper(), jour, Decimal(m["montant"]), m["vue"]


def construire_annotations(dossier: Path = DOSSIER_BRUT) -> list[Annotation]:
    """Lit tous les tickets de ``dossier`` et construit leurs annotations.

    Regroupement prudent (question Q-04) : deux fichiers de la même enseigne,
    au même montant, à 3 jours d'écart au plus, sont considérés comme un même
    ticket potentiel et placés dans le même groupe. On préfère perdre un peu
    de diversité plutôt que risquer une fuite entre entraînement et test.
    """
    brutes = []
    for chemin in sorted(dossier.rglob("*")):
        if not chemin.is_file() or chemin.name.startswith("."):
            continue
        entite, jour, montant, _vue = lire_nom(chemin.name)
        if chemin.parent.name.upper() != entite:
            raise NomInvalide(f"{chemin} n'est pas dans le dossier de son enseigne")
        groupe_base = MOTIF_NOM.match(chemin.name)
        cle = f"{entite}_{groupe_base['annee']}-{groupe_base['jour']}-{groupe_base['mois']}_{montant}"
        brutes.append((chemin.relative_to(dossier).as_posix(), entite, jour, montant, cle))

    # Fusion des quasi-doublons (même enseigne, même montant, <= 3 jours).
    groupe_de: dict[str, str] = {}
    par_montant: dict[tuple[str, Decimal], list[tuple[date, str]]] = defaultdict(list)
    for _f, entite, jour, montant, cle in brutes:
        candidats = par_montant[(entite, montant)]
        proche = next((g for d, g in candidats if abs((d - jour).days) <= 3), None)
        groupe_de[cle] = proche or cle
        candidats.append((jour, groupe_de[cle]))

    return [
        Annotation(f, entite, jour, montant, "EUR", groupe_de[cle])
        for f, entite, jour, montant, cle in brutes
    ]


def decouper(annotations: list[Annotation], graine: int = GRAINE) -> dict[str, str]:
    """Attribue chaque groupe à ``train``, ``validation`` ou ``test``.

    Par enseigne : on mélange les groupes avec une graine fixe, puis on réserve
    ``ceil(15 %)`` des groupes au test et autant à la validation (au moins 1).

    Retourne un dictionnaire ``groupe -> partition``.
    """
    groupes_par_entite: dict[str, list[str]] = defaultdict(list)
    for a in annotations:
        if a.groupe not in groupes_par_entite[a.entity]:
            groupes_par_entite[a.entity].append(a.groupe)

    generateur = random.Random(graine)
    partition: dict[str, str] = {}
    for entite in sorted(groupes_par_entite):
        groupes = sorted(groupes_par_entite[entite])
        generateur.shuffle(groupes)
        n_test = max(1, math.ceil(len(groupes) * PART_TEST))
        n_val = max(1, math.ceil(len(groupes) * PART_VALIDATION))
        for i, g in enumerate(groupes):
            partition[g] = "test" if i < n_test else "validation" if i < n_test + n_val else "train"
    return partition


def charger_annotations(fichier: Path = FICHIER_ANNOTATIONS) -> list[dict[str, str]]:
    """Relit ``annotations.csv`` joint à ``split.csv`` (une ligne par fichier)."""
    with open(FICHIER_SPLIT, encoding="utf-8") as f:
        split = {ligne["groupe"]: ligne["partition"] for ligne in csv.DictReader(f)}
    with open(fichier, encoding="utf-8") as f:
        lignes = list(csv.DictReader(f))
    for ligne in lignes:
        ligne["partition"] = split[ligne["groupe"]]
    return lignes


def main() -> None:
    """Génère les fichiers d'annotations et affiche les effectifs agrégés."""
    annotations = construire_annotations()
    FICHIER_ANNOTATIONS.parent.mkdir(parents=True, exist_ok=True)
    with open(FICHIER_ANNOTATIONS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fichier", "entity", "date", "total_amount", "currency", "groupe"])
        for a in annotations:
            w.writerow([a.fichier, a.entity, a.date.isoformat(), str(a.total_amount),
                        a.currency, a.groupe])

    # Le découpage n'est créé qu'une seule fois : on ne le régénère jamais,
    # pour ne pas « retoucher » le jeu de test après avoir vu des résultats.
    if FICHIER_SPLIT.exists():
        print(f"{FICHIER_SPLIT} existe déjà : découpage conservé tel quel.")
        with open(FICHIER_SPLIT, encoding="utf-8") as f:
            partition = {ligne["groupe"]: ligne["partition"] for ligne in csv.DictReader(f)}
    else:
        partition = decouper(annotations)
        with open(FICHIER_SPLIT, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["groupe", "partition"])
            for groupe, part in sorted(partition.items()):
                w.writerow([groupe, part])

    effectifs = Counter((a.entity, partition[a.groupe]) for a in annotations)
    print(f"{len(annotations)} fichiers, {len(partition)} tickets distincts")
    for entite in sorted({a.entity for a in annotations}):
        ligne = {p: effectifs[(entite, p)] for p in ("train", "validation", "test")}
        print(f"  {entite:<12} {ligne}")


if __name__ == "__main__":
    main()
