-- Migration 010: Memory Checkpoints + Timeline
-- Snapshot-uri logice ale memoriei proiectului

-- MEMORY_CHECKPOINTS - Salvare stare logică
CREATE TABLE IF NOT EXISTS memory_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    model TEXT,
    intent TEXT,
    context_mode TEXT,
    decisions_count INTEGER DEFAULT 0,
    facts_count INTEGER DEFAULT 0,
    goals_count INTEGER DEFAULT 0,
    tasks_count INTEGER DEFAULT 0,
    patterns_count INTEGER DEFAULT 0,
    restored_count INTEGER DEFAULT 0
);

-- CHECKPOINT_DATA - Snapshot JSON per entitate
CREATE TABLE IF NOT EXISTS checkpoint_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checkpoint_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    FOREIGN KEY (checkpoint_id) REFERENCES memory_checkpoints(id)
);

-- TIMELINE_EVENTS - Evenimente cronologice
CREATE TABLE IF NOT EXISTS timeline_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    event_id INTEGER,
    title TEXT NOT NULL,
    detail TEXT,
    project_path TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_mchk_project ON memory_checkpoints(project_path);
CREATE INDEX IF NOT EXISTS idx_mchk_created ON memory_checkpoints(created_at);
CREATE INDEX IF NOT EXISTS idx_mchk_name ON memory_checkpoints(name);

CREATE INDEX IF NOT EXISTS idx_chkdata_checkpoint ON checkpoint_data(checkpoint_id);
CREATE INDEX IF NOT EXISTS idx_chkdata_type ON checkpoint_data(entity_type);
CREATE INDEX IF NOT EXISTS idx_chkdata_entity ON checkpoint_data(entity_type, entity_id);

CREATE INDEX IF NOT EXISTS idx_timeline_project ON timeline_events(project_path);
CREATE INDEX IF NOT EXISTS idx_timeline_created ON timeline_events(created_at);
CREATE INDEX IF NOT EXISTS idx_timeline_type ON timeline_events(event_type);
