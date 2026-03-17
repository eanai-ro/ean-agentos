-- 020_cli_agent_columns.sql
-- Adaugă cli_name și agent_name la messages și sessions
-- Pentru a identifica ce CLI și ce agent a generat fiecare mesaj/sesiune

ALTER TABLE messages ADD COLUMN cli_name TEXT;
ALTER TABLE messages ADD COLUMN agent_name TEXT;
ALTER TABLE sessions ADD COLUMN cli_name TEXT;
ALTER TABLE sessions ADD COLUMN agent_name TEXT;

CREATE INDEX IF NOT EXISTS idx_messages_cli ON messages(cli_name);
CREATE INDEX IF NOT EXISTS idx_sessions_cli ON sessions(cli_name);
