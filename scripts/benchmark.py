"""Mesures de performance de la chaîne distribuée (cahier des charges §11.2).

Dépose des tickets via l'API, attend la fin de tous les traitements, puis
calcule à partir du journal des étapes :
    * temps de bout en bout (dépôt -> ``extraction.completed``) ;
    * temps de traitement par service (MS1, MS2, MS3) ;
    * temps d'attente dans les files RabbitMQ (avant chaque étape) ;
    * débit (documents par minute).

Deux modes :
    --sequentiel : un document à la fois (latence « à vide », comparable au monolithe)
    (défaut)     : tous les documents déposés d'un coup (charge, files qui se remplissent)

Usage :
    .venv/bin/python scripts/benchmark.py --nombre 60 --libelle charge-1xMS2
    .venv/bin/python scripts/benchmark.py --nombre 20 --sequentiel --libelle sequentiel

Seuls des agrégats sont affichés ; le détail par document va dans reports/raw/.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

import httpx

API = "http://localhost:8000"
ETAPES = {"pretraitement": "preprocessing.completed", "ocr": "ocr.completed",
          "extraction": "extraction.completed"}


def choisir_fichiers(nombre: int) -> list[Path]:
    """Sélection déterministe et équilibrée : on alterne les enseignes."""
    par_enseigne = [sorted(f for f in Path("data/raw", e).iterdir() if not f.name.startswith("."))
                    for e in ("carrefour", "lidl", "intermarche")]
    fichiers: list[Path] = []
    i = 0
    while len(fichiers) < nombre and any(i < len(l) for l in par_enseigne):  # noqa: E741
        for liste in par_enseigne:
            if i < len(liste) and len(fichiers) < nombre:
                fichiers.append(liste[i])
        i += 1
    return fichiers


def deposer(client: httpx.Client, fichier: Path) -> str:
    r = client.post(f"{API}/documents", files={"fichier": ("ticket", fichier.read_bytes())})
    r.raise_for_status()
    return r.json()["document_id"]


def attendre(client: httpx.Client, ids: list[str], delai: float = 900) -> dict[str, dict]:
    fin, resultats = time.time() + delai, {}
    while len(resultats) < len(ids) and time.time() < fin:
        for i in ids:
            if i not in resultats:
                d = client.get(f"{API}/documents/{i}").json()
                # COMPLETED est écrit par MS3 juste avant que son événement
                # extraction.completed soit journalisé : on attend les deux.
                if d["status"] == "FAILED" or (d["status"] == "COMPLETED" and d["duree_totale_ms"]):
                    resultats[i] = d
        time.sleep(0.3)
    return resultats


def _ts(texte: str) -> datetime:
    return datetime.fromisoformat(texte)


def analyser(docs: dict[str, dict]) -> dict:
    """Agrège les durées depuis le journal des étapes de chaque document."""
    e2e, debuts, fins = [], [], []
    services: dict[str, list[int]] = {k: [] for k in ETAPES}
    attentes: dict[str, list[int]] = {k: [] for k in ETAPES}
    for d in docs.values():
        if d["status"] != "COMPLETED":
            continue
        e2e.append(d["duree_totale_ms"])
        debuts.append(_ts(d["created_at"]))
        for e in d["etapes"]:
            if e["event_type"] == "extraction.completed":
                fins.append(_ts(e["emis_le"]))
            for etape, type_fin in ETAPES.items():
                if e["event_type"] == type_fin and e["duree_ms"] is not None:
                    services[etape].append(e["duree_ms"])
            if e["event_type"] == "step.started" and e["attente_ms"] is not None:
                attentes[e["details"]["etape"]].append(e["attente_ms"])

    def resume(valeurs: list[int]) -> dict:
        if not valeurs:
            return {}
        v = sorted(valeurs)
        return {"moyenne": round(statistics.mean(v)), "mediane": v[len(v) // 2],
                "p95": v[min(len(v) - 1, int(0.95 * len(v)))], "max": v[-1]}

    duree_totale = (max(fins) - min(debuts)).total_seconds() if fins else 0
    return {
        "documents": len(docs),
        "termines": len(e2e),
        "echecs": sum(d["status"] == "FAILED" for d in docs.values()),
        "bout_en_bout_ms": resume(e2e),
        "service_ms": {k: resume(v) for k, v in services.items()},
        "attente_file_ms": {k: resume(v) for k, v in attentes.items()},
        "duree_campagne_s": round(duree_totale, 1),
        "debit_docs_par_min": round(60 * len(e2e) / duree_totale, 1) if duree_totale else None,
    }


def main() -> None:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--nombre", type=int, default=30)
    parseur.add_argument("--sequentiel", action="store_true")
    parseur.add_argument("--echauffement", type=int, default=3, help="documents non comptés")
    parseur.add_argument("--libelle", default="mesure")
    args = parseur.parse_args()

    fichiers = choisir_fichiers(args.nombre + args.echauffement)
    with httpx.Client(timeout=30) as client:
        # Échauffement : charge les modèles Tesseract et scikit-learn en mémoire.
        attendre(client, [deposer(client, f) for f in fichiers[: args.echauffement]])
        mesures = fichiers[args.echauffement:]
        if args.sequentiel:
            docs = {}
            for f in mesures:
                docs.update(attendre(client, [deposer(client, f)]))
        else:
            docs = attendre(client, [deposer(client, f) for f in mesures])

    resultat = {"libelle": args.libelle, "mode": "sequentiel" if args.sequentiel else "charge",
                **analyser(docs)}
    Path("reports/raw").mkdir(parents=True, exist_ok=True)
    Path(f"reports/raw/bench_{args.libelle}.json").write_text(
        json.dumps({"resume": resultat, "documents": docs}, indent=2, default=str), encoding="utf-8")
    Path("reports/mesures").mkdir(parents=True, exist_ok=True)
    Path(f"reports/mesures/{args.libelle}.json").write_text(json.dumps(resultat, indent=2),
                                                           encoding="utf-8")
    print(json.dumps(resultat, indent=2))


if __name__ == "__main__":
    main()
