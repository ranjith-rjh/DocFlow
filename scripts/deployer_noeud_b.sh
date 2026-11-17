#!/usr/bin/env bash
# Déploie (ou met à jour) le nœud B sur la VM Fedora, depuis le Mac.
#
#     ./scripts/deployer_noeud_b.sh
#
# Copie le code de MS3, le schéma SQL et le modèle entraîné dans la VM via SSH,
# puis lance l'installation avec sudo. Le mot de passe SSH (si aucune clé
# n'est installée) et le mot de passe sudo de dfadmin sont demandés par la VM.
set -euo pipefail
cd "$(dirname "$0")/.."

[[ -f .env ]] || { echo "Lancer d'abord : ./scripts/configurer_env.sh distribue" >&2; exit 1; }
set -a; source .env; set +a
[[ "${DOCFLOW_MODE:-}" == "distribue" ]] || {
    echo "Le .env est en mode « ${DOCFLOW_MODE:-?} » : ./scripts/configurer_env.sh distribue" >&2; exit 1; }

VM_USER="${VM_USER:-dfadmin}"
CIBLE="$VM_USER@$FEDORA_IP"
[[ -f models/docflow-extraction.joblib ]] || \
    echo "Attention : models/docflow-extraction.joblib absent, MS3 utilisera la baseline par règles."

# Secrets transmis à l'installation puis supprimés de la VM.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
umask 077
cat > "$TMP/secrets.env" <<EOF
RABBITMQ_URL=amqp://$RABBITMQ_USER:$RABBITMQ_PASSWORD@$MAC_IP:5672/
DB_API_PASSWORD=$DB_API_PASSWORD
DB_MS3_PASSWORD=$DB_MS3_PASSWORD
MAC_IP=$MAC_IP
EXTRACTION_MODE=${EXTRACTION_MODE:-modele}
EOF

echo "==> Copie vers $CIBLE:~/docflow-deploiement"
mkdir -p models
COPYFILE_DISABLE=1 tar czf - --exclude '__pycache__' --exclude '*.egg-info' \
    pyproject.toml src deploy models -C "$TMP" secrets.env \
  | ssh "$CIBLE" 'rm -rf ~/docflow-deploiement && mkdir -p ~/docflow-deploiement && tar xzf - -C ~/docflow-deploiement'

echo "==> Installation (mot de passe sudo de $VM_USER demandé)"
ssh -t "$CIBLE" 'sudo bash ~/docflow-deploiement/deploy/fedora/installer_noeud_b.sh ~/docflow-deploiement/secrets.env; rm -f ~/docflow-deploiement/secrets.env'
