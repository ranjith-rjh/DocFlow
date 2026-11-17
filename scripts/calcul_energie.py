"""Calcul de l'énergie à partir de deux relevés powermetrics (voir mesurer_energie.sh).

    python scripts/calcul_energie.py <repos.txt> <charge.txt> <duree_s> <nb_docs> <gCO2e_par_kWh>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MOTIF = re.compile(r"Combined Power \(CPU \+ GPU \+ ANE\):\s*(\d+)\s*mW")


def puissances_mw(fichier: Path) -> list[int]:
    """Extrait les mesures « Combined Power » en milliwatts.

    Exemple :
        >>> import tempfile, os
        >>> f = Path(tempfile.mkstemp()[1]); _ = f.write_text("Combined Power (CPU + GPU + ANE): 1234 mW")
        >>> puissances_mw(f)
        [1234]
    """
    return [int(m) for m in MOTIF.findall(fichier.read_text(errors="ignore"))]


def main() -> None:
    repos, charge = puissances_mw(Path(sys.argv[1])), puissances_mw(Path(sys.argv[2]))
    duree_s, nb_docs, facteur = float(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5])
    if not repos or not charge:
        raise SystemExit("Aucune mesure « Combined Power » trouvée dans les relevés.")
    p_repos = sum(repos) / len(repos)
    p_charge = sum(charge) / len(charge)
    net_wh = max(p_charge - p_repos, 0) * duree_s / 3_600_000  # mW·s -> Wh
    brut_wh = p_charge * duree_s / 3_600_000
    resultat = {
        "documents": nb_docs,
        "duree_s": duree_s,
        "puissance_repos_w": round(p_repos / 1000, 2),
        "puissance_charge_w": round(p_charge / 1000, 2),
        "energie_brute_wh": round(brut_wh, 3),
        "energie_nette_wh": round(net_wh, 3),
        "wh_par_document_net": round(net_wh / nb_docs, 4),
        "facteur_gco2e_par_kwh": facteur,
        "gco2e_par_document_net": round(net_wh / nb_docs / 1000 * facteur, 5),
        "echantillons": {"repos": len(repos), "charge": len(charge)},
        "perimetre": "SoC Apple (CPU+GPU+ANE) via powermetrics ; hors écran, RAM, alimentation",
    }
    Path("reports/mesures/energie.json").write_text(json.dumps(resultat, indent=2), encoding="utf-8")
    print(json.dumps(resultat, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
