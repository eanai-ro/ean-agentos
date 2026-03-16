-- Migration 009: Intelligence Layer
-- error_patterns: patternuri detectate automat din error_resolutions

CREATE TABLE IF NOT EXISTS error_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_signature TEXT NOT NULL,
    solution TEXT NOT NULL,
    count INTEGER DEFAULT 1,
    first_seen TEXT DEFAULT (datetime('now')),
    last_seen TEXT DEFAULT (datetime('now')),
    project_path TEXT,
    auto_promoted INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_error_patterns_sig ON error_patterns(error_signature);
CREATE INDEX IF NOT EXISTS idx_error_patterns_count ON error_patterns(count DESC);
CREATE INDEX IF NOT EXISTS idx_error_patterns_project ON error_patterns(project_path);
