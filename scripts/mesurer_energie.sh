#!/usr/bin/env bash
# Estimation du coût énergétique d'une série de traitements (§11.3, T-12).
#
#     ./scripts/mesurer_energie.sh            # 60 documents
#     N=100 ./scripts/mesurer_energie.sh
#
# Méthode : powermetrics (outil Apple, nécessite sudo) mesure la puissance
# « Combined Power (CPU + GPU + ANE) » du SoC chaque seconde :
#   1. au repos pendant REPOS secondes (application lancée, aucun document) ;
#   2. pendant le traitement de N documents.
# Énergie nette = (puissance moyenne en charge − au repos) × durée.
#
# Limites (à rappeler dans le rapport) : seule la puce est mesurée (pas
# l'écran, la RAM ni l'alimentation) ; Docker Desktop et VirtualBox ajoutent
# leur propre consommation ; tout autre logiciel actif fausse la mesure.
set -euo pipefail
cd "$(dirname "$0")/.."

N="${N:-60}"
REPOS="${REPOS:-30}"
FACTEUR="${FACTEUR_CO2_G_KWH:-52}"  # gCO2e/kWh, à vérifier et citer (voir rapport)
mkdir -p reports/raw reports/mesures

curl -sf http://localhost:8000/health >/dev/null || { echo "Lancer l'application d'abord." >&2; exit 1; }
echo "powermetrics a besoin des droits administrateur :"
sudo -v

echo "1/2 Mesure au repos ($REPOS s) — ne touchez à rien…"
sudo powermetrics --samplers cpu_power,gpu_power -i 1000 -n "$REPOS" > reports/raw/energie_repos.txt

echo "2/2 Mesure pendant le traitement de $N documents…"
sudo powermetrics --samplers cpu_power,gpu_power -i 1000 > reports/raw/energie_charge.txt &
PM=$!
debut=$(date +%s)
.venv/bin/python scripts/benchmark.py --nombre "$N" --echauffement 0 --libelle energie > /dev/null
fin=$(date +%s)
sudo kill "$PM"
wait "$PM" 2>/dev/null || true

.venv/bin/python scripts/calcul_energie.py reports/raw/energie_repos.txt \
    reports/raw/energie_charge.txt "$((fin - debut))" "$N" "$FACTEUR"
