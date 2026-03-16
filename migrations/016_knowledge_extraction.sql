-- Migration 016: Knowledge Extraction V1 (Faza 17X)
-- Adaugă coloane pentru tracking auto-extraction pe tabelele existente.

ALTER TABLE decisions ADD COLUMN auto_extracted INTEGER DEFAULT 0;
ALTER TABLE decisions ADD COLUMN extraction_confidence REAL;
ALTER TABLE decisions ADD COLUMN source_session_id TEXT;

ALTER TABLE learned_facts ADD COLUMN auto_extracted INTEGER DEFAULT 0;
ALTER TABLE learned_facts ADD COLUMN extraction_confidence REAL;
ALTER TABLE learned_facts ADD COLUMN source_session_id TEXT;

ALTER TABLE error_resolutions ADD COLUMN auto_extracted INTEGER DEFAULT 0;
ALTER TABLE error_resolutions ADD COLUMN extraction_confidence REAL;
ALTER TABLE error_resolutions ADD COLUMN source_session_id TEXT;
