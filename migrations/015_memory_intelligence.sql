-- Migration 015: Memory Intelligence Layer
-- New tables: agent_reputation, experience_links

-- AGENT_REPUTATION — cross-agent weight tracking
CREATE TABLE IF NOT EXISTS agent_reputation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL UNIQUE,
    total_contributions INTEGER DEFAULT 0,
    successful_contributions INTEGER DEFAULT 0,
    failed_contributions INTEGER DEFAULT 0,
    promoted_count INTEGER DEFAULT 0,
    weight REAL DEFAULT 1.0,
    last_updated TEXT DEFAULT (datetime('now')),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_agent_rep_name ON agent_reputation(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_rep_weight ON agent_reputation(weight DESC);

-- EXPERIENCE_LINKS — logical graph connecting problems → errors → resolutions
CREATE TABLE IF NOT EXISTS experience_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_table TEXT NOT NULL,
    from_id INTEGER NOT NULL,
    to_table TEXT NOT NULL,
    to_id INTEGER NOT NULL,
    link_type TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    created_at TEXT DEFAULT (datetime('now')),
    created_by TEXT DEFAULT 'auto'
);

CREATE INDEX IF NOT EXISTS idx_explinks_from ON experience_links(from_table, from_id);
CREATE INDEX IF NOT EXISTS idx_explinks_to ON experience_links(to_table, to_id);
CREATE INDEX IF NOT EXISTS idx_explinks_type ON experience_links(link_type);
CREATE INDEX IF NOT EXISTS idx_explinks_created ON experience_links(created_at);
