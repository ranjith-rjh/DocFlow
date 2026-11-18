#!/usr/bin/env bash
# Installe le nœud B sur la VM Fedora : PostgreSQL + MS3.
# À lancer dans la VM, depuis le dossier copié du Mac :
#     sudo bash docflow/fedora/installer.sh
# Peut être relancé sans risque (mise à jour du code ou du modèle).
set -e
cd "$(dirname "$0")/.."
source .env

echo "== 1. PostgreSQL"
dnf install -y -q postgresql-server python3
[ -f /var/lib/pgsql/data/PG_VERSION ] || postgresql-setup --initdb
# Écouter le réseau, et n'accepter que le réseau privé (192.168.56.x) et la VM elle-même.
grep -q "^listen_addresses = '\*'" /var/lib/pgsql/data/postgresql.conf \
  || echo "listen_addresses = '*'" >> /var/lib/pgsql/data/postgresql.conf
grep -q "docflow" /var/lib/pgsql/data/pg_hba.conf \
  || sed -i '1i host docflow docflow 192.168.56.0/24 scram-sha-256\nhost docflow docflow 127.0.0.1/32 scram-sha-256' \
       /var/lib/pgsql/data/pg_hba.conf
systemctl enable postgresql
systemctl restart postgresql

echo "== 2. Base et utilisateur docflow"
sudo -u postgres psql -qc "CREATE USER docflow" 2>/dev/null || true
sudo -u postgres psql -qc "ALTER USER docflow PASSWORD '$DB_PASSWORD'"
sudo -u postgres createdb -O docflow docflow 2>/dev/null || true
PGPASSWORD="$DB_PASSWORD" psql -q -h 127.0.0.1 -U docflow -d docflow -f schema.sql

echo "== 3. MS3"
mkdir -p /opt/docflow/models
cp commun.py ms3_extraction.py /opt/docflow/
cp models/*.joblib /opt/docflow/models/ 2>/dev/null || echo "   (pas de modèle : enseigne par règles)"
[ -d /opt/docflow/venv ] || python3 -m venv /opt/docflow/venv
/opt/docflow/venv/bin/pip install -q -r requirements-ms3.txt
cat > /opt/docflow/ms3.env <<EOF
RABBITMQ_URL=amqp://$RABBITMQ_USER:$RABBITMQ_PASSWORD@192.168.56.1:5672/
DATABASE_URL=postgresql://docflow:$DB_PASSWORD@127.0.0.1:5432/docflow
MODELE=/opt/docflow/models/modele_enseigne.joblib
EOF
chmod 600 /opt/docflow/ms3.env
cp fedora/docflow-ms3.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable docflow-ms3
systemctl restart docflow-ms3

echo "== Terminé. Journal de MS3 : sudo journalctl -u docflow-ms3 -f"
sleep 3
systemctl is-active docflow-ms3
