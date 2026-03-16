-- ============================================================
-- Migration 012: Memory Branches
-- Git-like branching for memory entities
-- ============================================================

-- MEMORY_BRANCHES — branch registry
CREATE TABLE IF NOT EXISTS memory_branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    project_path TEXT NOT NULL,
    parent_branch TEXT DEFAULT 'main',
    description TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    created_by TEXT DEFAULT 'user',
    is_active INTEGER DEFAULT 1,
    UNIQUE(name, project_path)
);

-- BRANCH_MERGE_LOG — merge history
CREATE TABLE IF NOT EXISTS branch_merge_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_branch TEXT NOT NULL,
    target_branch TEXT NOT NULL,
    project_path TEXT NOT NULL,
    strategy TEXT DEFAULT 'merge',
    conflicts_found INTEGER DEFAULT 0,
    conflicts_resolved INTEGER DEFAULT 0,
    entities_merged INTEGER DEFAULT 0,
    merged_at TEXT DEFAULT (datetime('now')),
    merged_by TEXT DEFAULT 'user',
    notes TEXT
);

-- Add branch column to entity tables
-- ALTER TABLE is idempotent (we catch errors for existing columns)

-- decisions
ALTER TABLE decisions ADD COLUMN branch TEXT DEFAULT 'main';

-- goals
ALTER TABLE goals ADD COLUMN branch TEXT DEFAULT 'main';

-- tasks
ALTER TABLE tasks ADD COLUMN branch TEXT DEFAULT 'main';

-- learned_facts
ALTER TABLE learned_facts ADD COLUMN branch TEXT DEFAULT 'main';

-- error_resolutions
ALTER TABLE error_resolutions ADD COLUMN branch TEXT DEFAULT 'main';

-- INDEXES
CREATE INDEX IF NOT EXISTS idx_branches_project ON memory_branches(project_path);
CREATE INDEX IF NOT EXISTS idx_branches_name ON memory_branches(name, project_path);
CREATE INDEX IF NOT EXISTS idx_branches_active ON memory_branches(is_active);

CREATE INDEX IF NOT EXISTS idx_merge_log_project ON branch_merge_log(project_path);
CREATE INDEX IF NOT EXISTS idx_merge_log_source ON branch_merge_log(source_branch);
CREATE INDEX IF NOT EXISTS idx_merge_log_target ON branch_merge_log(target_branch);

CREATE INDEX IF NOT EXISTS idx_decisions_branch ON decisions(branch);
CREATE INDEX IF NOT EXISTS idx_goals_branch ON goals(branch);
CREATE INDEX IF NOT EXISTS idx_tasks_branch ON tasks(branch);
CREATE INDEX IF NOT EXISTS idx_facts_branch ON learned_facts(branch);
CREATE INDEX IF NOT EXISTS idx_resolutions_branch ON error_resolutions(branch);
