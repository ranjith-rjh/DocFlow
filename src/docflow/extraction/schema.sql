-- Schéma PostgreSQL de DocFlow AI (nœud B, Fedora).
-- Idempotent : peut être rejoué sans erreur ni perte de données.

DO $$ BEGIN
    CREATE TYPE statut_document AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Un document déposé et son état de traitement (créé par l'API).
CREATE TABLE IF NOT EXISTS documents (
    document_id    TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    format_source  TEXT NOT NULL,
    taille_octets  INTEGER NOT NULL CHECK (taille_octets > 0),
    original_ref   TEXT NOT NULL,          -- storage://… côté Mac, jamais le nom d'origine
    status         statut_document NOT NULL DEFAULT 'PENDING',
    erreur         TEXT,                   -- cause lisible, sans contenu du ticket
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Résultat métier : une seule ligne par document (idempotence, NF-07).
CREATE TABLE IF NOT EXISTS resultats (
    document_id       TEXT PRIMARY KEY REFERENCES documents(document_id) ON DELETE CASCADE,
    entity            TEXT NOT NULL CHECK (entity IN ('CARREFOUR', 'LIDL', 'INTERMARCHE', 'UNKNOWN')),
    date              DATE,
    total_amount      NUMERIC(10, 2) CHECK (total_amount IS NULL OR total_amount > 0),
    currency          CHAR(3),
    confidence        JSONB NOT NULL DEFAULT '{}'::jsonb,
    methode           JSONB NOT NULL DEFAULT '{}'::jsonb,
    champs_manquants  TEXT[] NOT NULL DEFAULT '{}',
    champs_incertains TEXT[] NOT NULL DEFAULT '{}',
    version_modele    TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Journal des étapes : un événement = une ligne, jamais deux (clé = event_id).
CREATE TABLE IF NOT EXISTS journal_etapes (
    event_id      TEXT PRIMARY KEY,
    document_id   TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    event_type    TEXT NOT NULL,
    service       TEXT NOT NULL,
    emis_le       TIMESTAMPTZ NOT NULL,
    duree_ms      INTEGER,
    attente_ms    INTEGER,
    details       JSONB NOT NULL DEFAULT '{}'::jsonb,
    enregistre_le TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS journal_etapes_document ON journal_etapes (document_id, emis_le);
CREATE INDEX IF NOT EXISTS documents_recents ON documents (created_at DESC);
