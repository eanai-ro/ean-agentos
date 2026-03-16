-- Migration 011: Agent Activity Log
-- Tracking activitate agent/model per acțiune

CREATE TABLE IF NOT EXISTS agent_activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Identificare sesiune/proiect
    session_id TEXT,
    project_path TEXT,
    -- Agent/model info
    agent_name TEXT,                    -- 'claude-opus', 'dana', 'vlad', etc.
    model_id TEXT,                      -- 'claude-opus-4', 'glm-5', etc.
    provider TEXT,                      -- 'anthropic', 'z.ai', 'local'
    -- Acțiune
    action_type TEXT NOT NULL,          -- 'decision', 'fix', 'code_gen', 'review', 'query', 'learn', 'resolve'
    action_summary TEXT NOT NULL,       -- Descriere scurtă a acțiunii
    -- Context
    entity_type TEXT,                   -- 'decision', 'fact', 'goal', 'task', 'error', 'checkpoint'
    entity_id INTEGER,                  -- ID-ul entității afectate
    -- Rezultat
    success INTEGER DEFAULT 1,         -- 1=succes, 0=eșec
    error_message TEXT,                 -- Mesaj eroare dacă success=0
    duration_ms INTEGER,               -- Durata acțiunii în milisecunde
    tokens_used INTEGER,               -- Token-uri consumate (dacă disponibil)
    -- Metadata
    metadata_json TEXT,                 -- JSON cu detalii adiționale
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexuri pentru query-uri frecvente
CREATE INDEX IF NOT EXISTS idx_activity_project ON agent_activity_log(project_path);
CREATE INDEX IF NOT EXISTS idx_activity_agent ON agent_activity_log(agent_name);
CREATE INDEX IF NOT EXISTS idx_activity_model ON agent_activity_log(model_id);
CREATE INDEX IF NOT EXISTS idx_activity_type ON agent_activity_log(action_type);
CREATE INDEX IF NOT EXISTS idx_activity_created ON agent_activity_log(created_at);
CREATE INDEX IF NOT EXISTS idx_activity_session ON agent_activity_log(session_id);
CREATE INDEX IF NOT EXISTS idx_activity_entity ON agent_activity_log(entity_type, entity_id);
