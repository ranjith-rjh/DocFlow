-- Base DocFlow (sur la VM Fedora) : une seule table.
-- L'API crée la ligne au dépôt ; MS3 la complète à la fin du traitement.

CREATE TABLE IF NOT EXISTS documents (
    document_id      TEXT PRIMARY KEY,                -- ex. DOC-1A2B3C4D
    status           TEXT NOT NULL DEFAULT 'PENDING'  -- PENDING, PROCESSING, COMPLETED, FAILED
                     CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
    entity           TEXT,                            -- CARREFOUR, LIDL, INTERMARCHE ou UNKNOWN
    date             DATE,
    total_amount     NUMERIC(10, 2),                  -- jamais de float pour de l'argent
    currency         TEXT,
    methode_enseigne TEXT,                            -- modele ou regles
    durees           JSONB,                           -- durée de chaque service, en ms
    erreur           TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
