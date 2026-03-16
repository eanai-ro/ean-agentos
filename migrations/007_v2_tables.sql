-- ============================================================
-- V2 MIGRATION - 007_v2_tables.sql
-- Tabele noi pentru: decisions, goals, tasks, learned_facts, project_profiles
-- Data: 2026-03-11
-- ============================================================

-- DECISIONS - Decizii arhitecturale, tehnice, de proiect
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'technical',
        -- technical, architectural, tooling, convention, process
    status TEXT NOT NULL DEFAULT 'active',
        -- active, superseded, reconsidered, archived
    confidence TEXT DEFAULT 'high',
        -- high, medium, low
    rationale TEXT,
    alternatives_considered TEXT,           -- JSON array
    superseded_by INTEGER,                  -- FK → decisions.id
    stale_after_days INTEGER DEFAULT 90,
    project_path TEXT,
    source_session TEXT,
    created_by TEXT DEFAULT 'user',          -- user, claude, auto
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (superseded_by) REFERENCES decisions(id)
);

CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions(status);
CREATE INDEX IF NOT EXISTS idx_decisions_category ON decisions(category);
CREATE INDEX IF NOT EXISTS idx_decisions_project ON decisions(project_path);
CREATE INDEX IF NOT EXISTS idx_decisions_created ON decisions(created_at);
CREATE INDEX IF NOT EXISTS idx_decisions_stale ON decisions(stale_after_days, created_at);
CREATE INDEX IF NOT EXISTS idx_decisions_project_status ON decisions(project_path, status);

-- GOALS - Obiective pe termen mediu/lung
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    priority TEXT NOT NULL DEFAULT 'medium',
        -- critical, high, medium, low
    status TEXT NOT NULL DEFAULT 'active',
        -- active, completed, paused, abandoned
    target_date TEXT,                       -- YYYY-MM-DD opțional
    completed_at TIMESTAMP,
    project_path TEXT,
    source_session TEXT,
    created_by TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
CREATE INDEX IF NOT EXISTS idx_goals_priority ON goals(priority);
CREATE INDEX IF NOT EXISTS idx_goals_project ON goals(project_path);
CREATE INDEX IF NOT EXISTS idx_goals_project_status ON goals(project_path, status);

-- TASKS - Acțiuni concrete, legate opțional de goals
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER,                        -- FK opțional → goals.id
    title TEXT NOT NULL,
    description TEXT,
    priority TEXT NOT NULL DEFAULT 'medium',
        -- critical, high, medium, low
    status TEXT NOT NULL DEFAULT 'todo',
        -- todo, in_progress, done, blocked, cancelled
    blocked_by TEXT,
    resolved_at TIMESTAMP,
    assigned_session TEXT,
    project_path TEXT,
    source_session TEXT,
    created_by TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (goal_id) REFERENCES goals(id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_goal ON tasks(goal_id);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_path);
CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_path, status);

-- LEARNED_FACTS - Cunoștințe dobândite
CREATE TABLE IF NOT EXISTS learned_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact TEXT NOT NULL,
    fact_type TEXT NOT NULL DEFAULT 'technical',
        -- technical, preference, convention, environment, gotcha
    category TEXT,                           -- categorie liberă (python, docker, git)
    confidence TEXT DEFAULT 'high',
        -- confirmed, high, medium, low
    is_pinned INTEGER DEFAULT 0,            -- 1 = apare mereu în context
    is_active INTEGER DEFAULT 1,            -- 0 = dezactivat/depășit
    source TEXT,                             -- URL, fișier, experiență
    superseded_by INTEGER,                  -- FK → learned_facts.id
    project_path TEXT,                      -- NULL = global
    source_session TEXT,
    created_by TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (superseded_by) REFERENCES learned_facts(id)
);

CREATE INDEX IF NOT EXISTS idx_facts_type ON learned_facts(fact_type);
CREATE INDEX IF NOT EXISTS idx_facts_pinned ON learned_facts(is_pinned);
CREATE INDEX IF NOT EXISTS idx_facts_active ON learned_facts(is_active);
CREATE INDEX IF NOT EXISTS idx_facts_project ON learned_facts(project_path);
CREATE INDEX IF NOT EXISTS idx_facts_category ON learned_facts(category);
CREATE INDEX IF NOT EXISTS idx_facts_project_active ON learned_facts(project_path, is_active);

-- PROJECT_PROFILES - Profil per proiect
CREATE TABLE IF NOT EXISTS project_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path TEXT NOT NULL UNIQUE,
    project_name TEXT,
    description TEXT,
    tech_stack TEXT,                         -- JSON array
    conventions TEXT,                        -- JSON object
    important_files TEXT,                    -- JSON array
    notes TEXT,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_sessions INTEGER DEFAULT 0,
    source_session TEXT,
    created_by TEXT DEFAULT 'auto',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_profiles_project ON project_profiles(project_path);
CREATE INDEX IF NOT EXISTS idx_profiles_last_active ON project_profiles(last_active_at);
