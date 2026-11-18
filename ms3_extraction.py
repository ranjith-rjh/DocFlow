"""MS3 — Extraction : du texte OCR à l'enseigne, la date et le total, puis PostgreSQL.

Tourne sur la VM Fedora. Écoute deux files :
    « extraction » : texte envoyé par MS2 -> extraire les 3 champs -> COMPLETED
    « erreurs »    : un service a échoué  -> FAILED avec la cause

Qui fait quoi :
    enseigne : modèle entraîné (entrainement.py) ; règles si le modèle est absent
    date     : règle (première date valide du ticket)
    total    : règle (montant de la ligne « TOTAL A PAYER », « A PAYER », « MONTANT DU »…)

Une valeur introuvable reste vide (None) : on n'invente jamais.
"""

import json
import os
import re
import unicodedata
from datetime import date
from decimal import Decimal
from pathlib import Path

import joblib
import psycopg

from commun import attendre_rabbitmq, lancer_service

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://docflow:docflow@localhost:5432/docflow")
CHEMIN_MODELE = Path(os.environ.get("MODELE", "models/modele_enseigne.joblib"))

ENSEIGNES = {"CARREFOUR": ["CARREFOUR"], "LIDL": ["LIDL"], "INTERMARCHE": ["INTERMARCHE"]}
LIBELLES_TOTAL = ["TOTAL A PAYER", "NET A PAYER", "MONTANT DU", "A PAYER", "TOTAL TTC", "TOTAL"]
PIEGES = ["SOUS-TOTAL", "SOUS TOTAL", "ELIGIBLE", "TOTAL TVA", "TOTAL HT", "PROMOTION"]
MONTANT = re.compile(r"(?<![\d.,])(\d{1,4}[.,]\d{2})(?![\d.,%])")
DATE = re.compile(r"(?<![\d/.-])(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})(?![\d/.-])")


# ------------------------------------------------------------------ règles
def normaliser(texte):
    """Majuscules sans accents : « Intermarché à payer » -> « INTERMARCHE A PAYER »."""
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return sans_accents.upper()


def montant(texte):
    """« 42,90 » -> Decimal('42.90'). Decimal évite les erreurs d'arrondi des float."""
    return Decimal(texte.replace(",", "."))


def enseigne_par_regles(texte):
    """L'enseigne dont le nom apparaît le plus souvent, sinon UNKNOWN."""
    texte = normaliser(texte)
    comptes = {nom: sum(texte.count(mot) for mot in mots) for nom, mots in ENSEIGNES.items()}
    meilleure = max(comptes, key=comptes.get)
    return meilleure if comptes[meilleure] > 0 else "UNKNOWN"


def trouver_date(texte, aujourd_hui=None):
    """Première date valide du ticket, entre 2015 et aujourd'hui.

    >>> trouver_date("LE 03-10-23 A 18:33", date(2026, 1, 1))
    datetime.date(2023, 10, 3)
    """
    aujourd_hui = aujourd_hui or date.today()
    for jour, mois, annee in DATE.findall(texte):
        annee = int(annee) + 2000 if len(annee) == 2 else int(annee)
        try:
            d = date(annee, int(mois), int(jour))
        except ValueError:
            continue  # ex. 31/02 : pas une vraie date
        if 2015 <= d.year and d <= aujourd_hui:
            return d
    return None


def trouver_total(texte):
    """Montant de la première ligne portant un libellé de total, par ordre de priorité.

    Sur la ligne trouvée, on prend le dernier montant (colonne de droite) ; si
    le montant est passé à la ligne suivante, on prend celui de la ligne suivante.

    >>> trouver_total("SOUS-TOTAL 3,02\\nA payer 3,02\\nTOTAL ELIGIBLE 3,96")
    Decimal('3.02')
    """
    lignes = [normaliser(ligne) for ligne in texte.splitlines() if ligne.strip()]
    for libelle in LIBELLES_TOTAL:
        for i, ligne in enumerate(lignes):
            if libelle in ligne and not any(p in ligne for p in PIEGES):
                montants = MONTANT.findall(ligne)
                if not montants and i + 1 < len(lignes):
                    montants = MONTANT.findall(lignes[i + 1])[:1]
                if montants:
                    return montant(montants[-1])
    return None


# ------------------------------------------------------------------ modèle
def charger_modele():
    if CHEMIN_MODELE.exists():
        print(f"[ms3] modèle chargé : {CHEMIN_MODELE}", flush=True)
        return joblib.load(CHEMIN_MODELE)
    print("[ms3] pas de modèle : enseigne par règles", flush=True)
    return None


def preparer_texte(texte):
    """Texte donné au modèle : normalisé, chiffres masqués (le modèle ne doit pas
    retenir un numéro de carte de fidélité ou un montant)."""
    return re.sub(r"\d", "0", normaliser(texte))


def extraire(texte, modele=None):
    """Extrait les trois champs d'un texte OCR."""
    if modele is not None:
        enseigne, methode = modele.predict([preparer_texte(texte)])[0], "modele"
    else:
        enseigne, methode = enseigne_par_regles(texte), "regles"
    total = trouver_total(texte)
    return {
        "entity": enseigne,
        "date": trouver_date(texte),
        "total_amount": total,
        "currency": "EUR" if total is not None else None,
        "methode_enseigne": methode,
    }


# ------------------------------------------------------------------ service
def enregistrer(document_id, resultat, durees):
    """Écrit le résultat. Un UPDATE sur la clé document_id est idempotent :
    recevoir deux fois le même message ne crée jamais de doublon."""
    with psycopg.connect(DATABASE_URL) as cx:
        cx.execute(
            """UPDATE documents SET status = 'COMPLETED', entity = %s, date = %s,
                   total_amount = %s, currency = %s, methode_enseigne = %s,
                   durees = %s, updated_at = now()
               WHERE document_id = %s""",
            (resultat["entity"], resultat["date"], resultat["total_amount"], resultat["currency"],
             resultat["methode_enseigne"], json.dumps(durees), document_id),
        )


def marquer_echec(message):
    with psycopg.connect(DATABASE_URL) as cx:
        cx.execute("UPDATE documents SET status = 'FAILED', erreur = %s, updated_at = now() "
                   "WHERE document_id = %s", (message["erreur"], message["document_id"]))


if __name__ == "__main__":
    MODELE = charger_modele()

    def traiter_extraction(message):
        durees = message.get("durees", {})
        enregistrer(message["document_id"], extraire(message["texte"], MODELE), durees)
        return None  # dernière étape : rien à publier

    def traiter_erreur(message):
        marquer_echec(message)
        return None

    attendre_rabbitmq()
    lancer_service("ms3", {"extraction": traiter_extraction, "erreurs": traiter_erreur})
