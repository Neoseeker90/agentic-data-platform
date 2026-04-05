-- 0002_sessions.sql
-- Adds conversation_turns table for session-scoped conversation memory.

CREATE TABLE IF NOT EXISTS conversation_turns (
    turn_id     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID        NOT NULL,
    run_id      UUID        REFERENCES runs(run_id) ON DELETE SET NULL,
    role        TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS conversation_turns_session_idx
    ON conversation_turns(session_id, created_at DESC);
