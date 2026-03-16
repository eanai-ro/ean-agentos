-- Migration 006: Observability & Audit Tables
-- Safe migrations cu IF NOT EXISTS
-- Data: 2026-02-08

-- === AUDIT TRAIL ===
-- Trasabilitate pentru orice modificare automată

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,                   -- ISO8601 timestamp
    action_type TEXT NOT NULL,          -- scrub, quarantine, panic_fix, restore, purge, backup, etc.
    table_name TEXT NOT NULL,           -- messages, tool_calls, errors, quarantine, etc.
    row_id TEXT,                        -- ID-ul rândului afectat (string generic)
    fingerprint TEXT,                   -- optional, pentru corelare (ex: error fingerprint)
    severity TEXT,                      -- INFO/WARN/HIGH/CRITICAL
    change_summary TEXT,                -- text scurt: ce s-a schimbat
    actor TEXT NOT NULL                 -- "system", "mem_panic", "guard", "scrubbing", etc.
);

CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action_type);
CREATE INDEX IF NOT EXISTS idx_audit_table ON audit_log(table_name);
CREATE INDEX IF NOT EXISTS idx_audit_severity ON audit_log(severity);

-- === FALSE POSITIVE SCORING ===
-- Pattern rules pentru scoring

CREATE TABLE IF NOT EXISTS detection_rules (
    pattern_id TEXT PRIMARY KEY,        -- unique ID pentru pattern (ex: "bearer_auth", "openai_key")
    category TEXT NOT NULL,             -- api_key, jwt, bearer, pem, password, oauth_token, etc.
    weight INTEGER NOT NULL,            -- 1-100 (weight pentru scoring)
    description TEXT,                   -- descriere pattern
    enabled INTEGER NOT NULL DEFAULT 1  -- 0=disabled, 1=enabled
);

CREATE INDEX IF NOT EXISTS idx_rules_enabled ON detection_rules(enabled);
CREATE INDEX IF NOT EXISTS idx_rules_category ON detection_rules(category);

-- === DETECTION EVENTS ===
-- Log pentru fiecare detectare (scrub/guard/panic)

CREATE TABLE IF NOT EXISTS detection_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,                   -- ISO8601
    source TEXT NOT NULL,               -- scrub|guard|panic
    pattern_id TEXT,                    -- FK către detection_rules
    category TEXT,                      -- category din rule
    score INTEGER NOT NULL,             -- 0-100
    confidence TEXT NOT NULL,           -- LOW|MED|HIGH
    table_name TEXT,                    -- unde a fost detectat
    row_id TEXT,                        -- row_id afectat
    excerpt TEXT,                       -- excerpt SCRUBBED (max 80 chars, niciodată secret!)
    decision TEXT NOT NULL              -- allow|scrub|quarantine|report
);

CREATE INDEX IF NOT EXISTS idx_det_ts ON detection_events(ts);
CREATE INDEX IF NOT EXISTS idx_det_score ON detection_events(score);
CREATE INDEX IF NOT EXISTS idx_det_source ON detection_events(source);
CREATE INDEX IF NOT EXISTS idx_det_pattern ON detection_events(pattern_id);
CREATE INDEX IF NOT EXISTS idx_det_decision ON detection_events(decision);

-- === INITIAL DETECTION RULES ===
-- Populare cu pattern-uri default

INSERT OR IGNORE INTO detection_rules (pattern_id, category, weight, description, enabled) VALUES
    ('pem_private', 'pem', 100, 'PEM private key (-----BEGIN)', 1),
    ('bearer_auth', 'bearer', 95, 'Authorization: Bearer header', 1),
    ('jwt_token', 'jwt', 90, 'JWT tokens (access_token, refresh_token)', 1),
    ('openai_key', 'api_key', 85, 'OpenAI API key (sk-...)', 1),
    ('github_token', 'api_key', 85, 'GitHub token (ghp_...)', 1),
    ('github_pat', 'api_key', 85, 'GitHub PAT (github_pat_...)', 1),
    ('aws_access_key', 'api_key', 85, 'AWS access key (AKIA...)', 1),
    ('google_key', 'api_key', 80, 'Google API key (AIza...)', 1),
    ('slack_token', 'oauth_token', 80, 'Slack token (xox...)', 1),
    ('generic_token', 'generic', 40, 'Generic long token (heuristic, >45 chars)', 1);

-- Comentariu: Migrația e safe (IF NOT EXISTS) și poate fi rulată de mai multe ori
