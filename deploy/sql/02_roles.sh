#!/usr/bin/env bash
# Initialisation du conteneur PostgreSQL (mode nœud B local) :
# crée les comptes applicatifs après le schéma (01_schema.sql).
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v api_pwd="$DOCFLOW_API_DB_PASSWORD" -v ms3_pwd="$DOCFLOW_MS3_DB_PASSWORD" \
     -f /docflow/roles.sql
