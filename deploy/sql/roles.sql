-- Comptes applicatifs aux droits minimaux (idempotent).
-- Variables psql attendues : api_pwd, ms3_pwd.
--
--   docflow_api : lit tout, crée des documents, peut marquer un échec de dépôt.
--   docflow_ms3 : écrit résultats et journal, met à jour les statuts.
-- Aucun des deux ne peut supprimer de données ni modifier le schéma.

SELECT 'CREATE ROLE docflow_api LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'docflow_api') \gexec
SELECT 'CREATE ROLE docflow_ms3 LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'docflow_ms3') \gexec

ALTER ROLE docflow_api WITH LOGIN PASSWORD :'api_pwd';
ALTER ROLE docflow_ms3 WITH LOGIN PASSWORD :'ms3_pwd';

GRANT CONNECT ON DATABASE docflow TO docflow_api, docflow_ms3;
GRANT USAGE ON SCHEMA public TO docflow_api, docflow_ms3;

GRANT SELECT ON documents, resultats, journal_etapes TO docflow_api;
GRANT INSERT ON documents TO docflow_api;
GRANT UPDATE (status, erreur, updated_at) ON documents TO docflow_api;

GRANT SELECT ON documents TO docflow_ms3;
GRANT UPDATE (status, erreur, updated_at) ON documents TO docflow_ms3;
GRANT SELECT, INSERT, UPDATE ON resultats, journal_etapes TO docflow_ms3;
