-- Migration 014: Cross-Agent Learning columns
-- Adds is_global + promoted_from_agent to decisions, learned_facts, error_resolutions

ALTER TABLE decisions ADD COLUMN is_global INTEGER DEFAULT 0;
ALTER TABLE decisions ADD COLUMN promoted_from_agent TEXT;

ALTER TABLE learned_facts ADD COLUMN is_global INTEGER DEFAULT 0;
ALTER TABLE learned_facts ADD COLUMN promoted_from_agent TEXT;

ALTER TABLE error_resolutions ADD COLUMN is_global INTEGER DEFAULT 0;
ALTER TABLE error_resolutions ADD COLUMN promoted_from_agent TEXT;

CREATE INDEX IF NOT EXISTS idx_decisions_global ON decisions(is_global);
CREATE INDEX IF NOT EXISTS idx_facts_global ON learned_facts(is_global);
CREATE INDEX IF NOT EXISTS idx_resolutions_global ON error_resolutions(is_global);
