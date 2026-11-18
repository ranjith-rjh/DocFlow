"""Mesures de temps : dépose N tickets d'un coup et mesure la chaîne complète.

Usage (application lancée) :
    docker compose run --rm outils python mesures.py 30

Affiche et ajoute dans reports/mesures.md :
    - durée moyenne de bout en bout (dépôt -> résultat en base) ;
    - durée moyenne de MS1 et de MS2 (enregistrées par les services eux-mêmes) ;
    - débit en tickets par minute.
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

API = os.environ.get("API_URL", "http://api:8000")
nombre = int(sys.argv[1]) if len(sys.argv) > 1 else 30

tous = sorted(f for f in Path("data/raw").rglob("*") if f.suffix in (".pdf", ".png", ".jpg"))
fichiers = tous[:: max(1, len(tous) // nombre)][:nombre]  # répartis sur les trois enseignes
ids = [requests.post(f"{API}/documents", files={"fichier": f.open("rb")}).json()["document_id"]
       for f in fichiers]
print(f"{len(ids)} tickets déposés, attente des résultats…")

while True:
    documents = [requests.get(f"{API}/documents/{i}").json() for i in ids]
    if all(d["status"] in ("COMPLETED", "FAILED") for d in documents):
        break
    time.sleep(1)

finis = [d for d in documents if d["status"] == "COMPLETED"]
debut = min(datetime.fromisoformat(d["created_at"]) for d in finis)
fin = max(datetime.fromisoformat(d["updated_at"]) for d in finis)
bout_en_bout = sum((datetime.fromisoformat(d["updated_at"]) - datetime.fromisoformat(d["created_at"]))
                   .total_seconds() for d in finis) / len(finis)
ms1 = sum(d["durees"]["ms1"] for d in finis) / len(finis)
ms2 = sum(d["durees"]["ms2"] for d in finis) / len(finis)
debit = len(finis) / (fin - debut).total_seconds() * 60

ligne = (f"| {datetime.now():%Y-%m-%d %H:%M} | {len(ids)} | {len(ids) - len(finis)} | {bout_en_bout:.1f} s "
         f"| {ms1:.0f} ms | {ms2:.0f} ms | {debit:.0f} tickets/min |")
rapport = Path("reports/mesures.md")
if not rapport.exists():
    rapport.write_text("# Mesures de temps\n\n| Date | Tickets | Échecs | Bout en bout (moy.) "
                       "| MS1 (moy.) | MS2 (moy.) | Débit |\n|---|---:|---:|---:|---:|---:|---:|\n")
with rapport.open("a") as f:
    f.write(ligne + "\n")
print(ligne)
