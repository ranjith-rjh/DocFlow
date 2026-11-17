#!/usr/bin/env bash
# Installe le nœud B de DocFlow sur Fedora : PostgreSQL + MS3 (service systemd).
#
# Lancé PAR scripts/deployer_noeud_b.sh (depuis le Mac), dans la VM, avec sudo :
#     sudo ./deploy/fedora/installer_noeud_b.sh <fichier_secrets>
#
# Idempotent : peut être relancé pour mettre à jour le code ou le modèle.
#
# Décision Q-05 : MS3 tourne dans un environnement virtuel Python sous
# systemd, sans Docker, pour garder la distinction conteneur (Mac) / VM (Fedora).
set -euo pipefail

SECRETS="${1:?Usage : sudo $0 <fichier_secrets>}"
SOURCE="$(cd "$(dirname "$0")/../.." && pwd)"
APP=/opt/docflow
ETC=/etc/docflow
PGDATA=/var/lib/pgsql/data

[[ $EUID -eq 0 ]] || { echo "À lancer avec sudo." >&2; exit 1; }
# shellcheck disable=SC1090
source "$SECRETS"
: "${RABBITMQ_URL:?}" "${DB_API_PASSWORD:?}" "${DB_MS3_PASSWORD:?}" "${MAC_IP:?}"

etape() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }

etape "1/7 Paquets système"
dnf install -y -q postgresql-server postgresql python3 python3-pip

etape "2/7 Initialisation de PostgreSQL"
if [[ ! -f "$PGDATA/PG_VERSION" ]]; then
    postgresql-setup --initdb
fi

# Écoute sur toutes les interfaces : l'accès est filtré par pg_hba.conf
# (réseau privé uniquement) et par la zone firewalld « docflow ». Écouter
# seulement 192.168.56.10 échouerait si docflow-net démarre après PostgreSQL.
sed -i '/# >>> docflow/,/# <<< docflow/d' "$PGDATA/postgresql.conf"
cat >> "$PGDATA/postgresql.conf" <<'EOF'
# >>> docflow
listen_addresses = '*'
password_encryption = 'scram-sha-256'
# <<< docflow
EOF

# Règles d'accès DocFlow placées en tête (la première règle qui correspond s'applique).
sed -i '/# >>> docflow/,/# <<< docflow/d' "$PGDATA/pg_hba.conf"
{
    echo "# >>> docflow"
    echo "host  docflow  docflow_ms3  127.0.0.1/32     scram-sha-256"
    echo "host  docflow  docflow_api  192.168.56.0/24  scram-sha-256"
    echo "# <<< docflow"
    cat "$PGDATA/pg_hba.conf"
} > "$PGDATA/pg_hba.conf.nouveau"
mv "$PGDATA/pg_hba.conf.nouveau" "$PGDATA/pg_hba.conf"
chown postgres:postgres "$PGDATA/pg_hba.conf"
chmod 600 "$PGDATA/pg_hba.conf"
restorecon -q "$PGDATA/pg_hba.conf" 2>/dev/null || true

systemctl enable -q postgresql
systemctl restart postgresql

etape "3/7 Base, schéma et comptes"
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='docflow'" | grep -q 1; then
    sudo -u postgres createdb docflow
fi
sudo -u postgres psql -q -v ON_ERROR_STOP=1 -d docflow < "$SOURCE/src/docflow/extraction/schema.sql"
sudo -u postgres psql -q -v ON_ERROR_STOP=1 -d docflow \
    -v api_pwd="$DB_API_PASSWORD" -v ms3_pwd="$DB_MS3_PASSWORD" < "$SOURCE/deploy/sql/roles.sql"

etape "4/7 Compte système et code de MS3"
id docflow &>/dev/null || useradd --system --home-dir "$APP" --shell /sbin/nologin docflow
mkdir -p "$APP/app" "$APP/models" "$ETC"
rm -rf "$APP/app/src"
cp -r "$SOURCE/pyproject.toml" "$SOURCE/src" "$APP/app/"
if compgen -G "$SOURCE/models/*.joblib" > /dev/null; then
    cp "$SOURCE"/models/*.joblib "$SOURCE"/models/*.json "$APP/models/" 2>/dev/null || true
else
    echo "Attention : aucun modèle fourni, MS3 utilisera la baseline par règles."
fi

etape "5/7 Environnement virtuel Python"
[[ -x "$APP/venv/bin/python" ]] || python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install -q --upgrade pip
"$APP/venv/bin/pip" install -q "$APP/app[ms3]"
chown -R docflow:docflow "$APP"

etape "6/7 Configuration et service systemd"
umask 027
cat > "$ETC/ms3.env" <<EOF
RABBITMQ_URL=$RABBITMQ_URL
DATABASE_URL=postgresql+psycopg://docflow_ms3:$DB_MS3_PASSWORD@127.0.0.1:5432/docflow
EXTRACTION_MODE=${EXTRACTION_MODE:-modele}
MODELE_CHEMIN=$APP/models/docflow-extraction.joblib
EOF
chown root:docflow "$ETC/ms3.env"
chmod 640 "$ETC/ms3.env"
install -m 644 "$SOURCE/deploy/fedora/docflow-ms3.service" /etc/systemd/system/docflow-ms3.service
systemctl daemon-reload
systemctl enable -q docflow-ms3
systemctl restart docflow-ms3

etape "7/7 Vérifications"
if timeout 3 bash -c "</dev/tcp/$MAC_IP/5672" 2>/dev/null; then
    echo "  [OK]    RabbitMQ joignable sur $MAC_IP:5672"
else
    echo "  [ECHEC] RabbitMQ injoignable sur $MAC_IP:5672 (docker compose est-il lancé sur le Mac ?)"
fi
systemctl is-active -q postgresql && echo "  [OK]    PostgreSQL actif" || echo "  [ECHEC] PostgreSQL inactif"
sleep 3
systemctl is-active -q docflow-ms3 && echo "  [OK]    docflow-ms3 actif" || echo "  [ECHEC] docflow-ms3 inactif"
echo
echo "Journaux de MS3 : sudo journalctl -u docflow-ms3 -f"
