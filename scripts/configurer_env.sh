#!/usr/bin/env bash
# Crée ou met à jour le fichier .env du Mac.
#
#   ./scripts/configurer_env.sh distribue   # MS3 + PostgreSQL sur la VM Fedora (cible)
#   ./scripts/configurer_env.sh local       # MS3 + PostgreSQL en conteneurs sur le Mac
#
# Les mots de passe sont générés aléatoirement à la première exécution, puis
# conservés : changer de mode ne les modifie pas. .env est ignoré par Git.
set -euo pipefail
cd "$(dirname "$0")/.."

MODE="${1:-}"
if [[ "$MODE" != "local" && "$MODE" != "distribue" ]]; then
    echo "Usage : $0 <local|distribue>" >&2
    exit 2
fi

FEDORA_IP="${FEDORA_IP:-192.168.56.10}"
MAC_IP="${MAC_IP:-192.168.56.1}"

# Relit une valeur existante du .env, sinon en génère une nouvelle.
valeur() {
    local nom="$1"
    if [[ -f .env ]] && grep -q "^${nom}=" .env; then
        grep "^${nom}=" .env | head -1 | cut -d= -f2-
    else
        openssl rand -hex 16
    fi
}

RABBITMQ_PASSWORD="$(valeur RABBITMQ_PASSWORD)"
DB_ADMIN_PASSWORD="$(valeur DB_ADMIN_PASSWORD)"
DB_API_PASSWORD="$(valeur DB_API_PASSWORD)"
DB_MS3_PASSWORD="$(valeur DB_MS3_PASSWORD)"

if [[ "$MODE" == "distribue" ]]; then
    RABBITMQ_BIND_IP="$MAC_IP"
    DB_HOTE="$FEDORA_IP:5432"
else
    RABBITMQ_BIND_IP="127.0.0.1"
    DB_HOTE="postgres:5432"
fi

umask 077
cat > .env <<EOF
# Généré par scripts/configurer_env.sh — NE PAS COMMITTER.
DOCFLOW_MODE=$MODE
COMPOSE_PROFILES=$([[ "$MODE" == "local" ]] && echo "noeud-b-local" || echo "")

# RabbitMQ (nœud A, Mac)
RABBITMQ_USER=docflow
RABBITMQ_PASSWORD=$RABBITMQ_PASSWORD
RABBITMQ_BIND_IP=$RABBITMQ_BIND_IP
MAC_IP=$MAC_IP

# PostgreSQL (nœud B : Fedora, ou conteneur en mode local)
FEDORA_IP=$FEDORA_IP
DB_ADMIN_PASSWORD=$DB_ADMIN_PASSWORD
DB_API_PASSWORD=$DB_API_PASSWORD
DB_MS3_PASSWORD=$DB_MS3_PASSWORD
API_DATABASE_URL=postgresql+psycopg://docflow_api:$DB_API_PASSWORD@$DB_HOTE/docflow

# Extraction : modele (hybride entraîné) ou regles (baseline)
EXTRACTION_MODE=modele
MAX_TENTATIVES=3
MAX_TAILLE_OCTETS=10485760
EOF

echo ".env écrit en mode « $MODE »."
if [[ "$MODE" == "distribue" ]]; then
    echo "RabbitMQ sera exposé sur $MAC_IP:5672 ; PostgreSQL attendu sur $FEDORA_IP:5432."
    echo "Étape suivante : ./scripts/deployer_noeud_b.sh"
fi
