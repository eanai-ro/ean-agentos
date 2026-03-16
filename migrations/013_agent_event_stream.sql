-- Migration 013: Agent Event Stream
-- Fine-grained execution/observability events for agents

CREATE TABLE IF NOT EXISTS agent_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path TEXT,
    session_id TEXT,
    branch_name TEXT,
    cli_name TEXT,
    agent_name TEXT,
    provider TEXT,
    model_name TEXT,
    event_type TEXT NOT NULL,
    event_phase TEXT DEFAULT 'end',
    title TEXT,
    summary TEXT,
    detail TEXT,
    status TEXT DEFAULT 'completed',
    related_table TEXT,
    related_id INTEGER,
    parent_event_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    started_at TEXT,
    finished_at TEXT,
    duration_ms INTEGER,
    success_flag INTEGER DEFAULT 1,
    metadata_json TEXT,
    FOREIGN KEY (parent_event_id) REFERENCES agent_events(id)
);

CREATE INDEX IF NOT EXISTS idx_ae_project ON agent_events(project_path);
CREATE INDEX IF NOT EXISTS idx_ae_session ON agent_events(session_id);
CREATE INDEX IF NOT EXISTS idx_ae_branch ON agent_events(branch_name);
CREATE INDEX IF NOT EXISTS idx_ae_agent ON agent_events(agent_name);
CREATE INDEX IF NOT EXISTS idx_ae_model ON agent_events(model_name);
CREATE INDEX IF NOT EXISTS idx_ae_type ON agent_events(event_type);
CREATE INDEX IF NOT EXISTS idx_ae_created ON agent_events(created_at);
CREATE INDEX IF NOT EXISTS idx_ae_success ON agent_events(success_flag);
CREATE INDEX IF NOT EXISTS idx_ae_parent ON agent_events(parent_event_id);
