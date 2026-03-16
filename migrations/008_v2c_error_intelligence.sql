-- ============================================================
-- V2C: Error Intelligence + Model Attribution (2026-03-11)
-- ============================================================
-- 2 tabele noi: error_resolutions, model_usage_log
-- ALTER TABLE pe decisions, learned_facts (+model_used, +provider)
-- ============================================================

-- ERROR_RESOLUTIONS - Rezolvări structurate pentru erori
CREATE TABLE IF NOT EXISTS error_resolutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_id INTEGER,                           -- FK → errors_solutions.id (NULL dacă eroarea e descrisă manual)
    error_fingerprint TEXT,                      -- hash normalizat pentru deduplicare
    error_summary TEXT,                          -- descriere scurtă dacă error_id e NULL

    resolution TEXT NOT NULL,                    -- ce s-a făcut
    resolution_code TEXT,                        -- snippet cod (opțional)
    resolution_type TEXT DEFAULT 'fix',          -- fix, workaround, config_change, dependency, rollback

    model_used TEXT,                             -- claude-opus-4-6, glm-5, etc.
    provider TEXT,                               -- anthropic, zai, qwen, local
    agent_name TEXT,                             -- dana, vlad, qa, etc. (NULL = utilizator direct)

    project_path TEXT,
    source_session TEXT,
    created_by TEXT DEFAULT 'user',              -- user, auto, claude
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),

    worked INTEGER DEFAULT 1,                   -- 1 = confirmat, 0 = nu, NULL = necunoscut
    reuse_count INTEGER DEFAULT 0,              -- de câte ori a fost reutilizată

    FOREIGN KEY (error_id) REFERENCES errors_solutions(id),
    FOREIGN KEY (source_session) REFERENCES sessions(session_id)
);

-- MODEL_USAGE_LOG - Logare model/provider per acțiune
CREATE TABLE IF NOT EXISTS model_usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    model_id TEXT NOT NULL,                     -- claude-opus-4-6, glm-5, kimi-k2.5
    provider TEXT,                              -- anthropic, zai, qwen, local
    agent_name TEXT,                            -- NULL = sesiune principală

    action_type TEXT NOT NULL,                  -- session_start, decision, fix, code_gen, review, query
    action_ref_table TEXT,                      -- decisions, error_resolutions, learned_facts, etc.
    action_ref_id INTEGER,                      -- ID-ul din tabela referită

    project_path TEXT,
    success_flag INTEGER,                       -- 1 = succes, 0 = eșec, NULL = necunoscut
    created_at TEXT DEFAULT (datetime('now')),
    metadata TEXT,                              -- JSON opțional (tokeni, durată, etc.)

    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- INDEXES: error_resolutions
CREATE INDEX IF NOT EXISTS idx_error_res_error_id ON error_resolutions(error_id);
CREATE INDEX IF NOT EXISTS idx_error_res_fingerprint ON error_resolutions(error_fingerprint);
CREATE INDEX IF NOT EXISTS idx_error_res_model ON error_resolutions(model_used);
CREATE INDEX IF NOT EXISTS idx_error_res_provider ON error_resolutions(provider);
CREATE INDEX IF NOT EXISTS idx_error_res_project ON error_resolutions(project_path);
CREATE INDEX IF NOT EXISTS idx_error_res_type ON error_resolutions(resolution_type);
CREATE INDEX IF NOT EXISTS idx_error_res_created ON error_resolutions(created_at);
CREATE INDEX IF NOT EXISTS idx_error_res_worked ON error_resolutions(worked);

-- INDEXES: model_usage_log
CREATE INDEX IF NOT EXISTS idx_model_log_session ON model_usage_log(session_id);
CREATE INDEX IF NOT EXISTS idx_model_log_model ON model_usage_log(model_id);
CREATE INDEX IF NOT EXISTS idx_model_log_provider ON model_usage_log(provider);
CREATE INDEX IF NOT EXISTS idx_model_log_action ON model_usage_log(action_type);
CREATE INDEX IF NOT EXISTS idx_model_log_ref ON model_usage_log(action_ref_table, action_ref_id);
CREATE INDEX IF NOT EXISTS idx_model_log_project ON model_usage_log(project_path);
CREATE INDEX IF NOT EXISTS idx_model_log_created ON model_usage_log(created_at);
