-- 0001_initial_schema.sql
-- Initial schema for the Agentic Data Platform.

-- Enable pgcrypto for gen_random_uuid() if not already available via pg core
-- (gen_random_uuid() is built-in from PG 13+; this guard is a no-op on PG 13+)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ─────────────────────────────────────────────
-- runs
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS runs (
    run_id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT        NOT NULL,
    interface       TEXT        NOT NULL,
    request_text    TEXT        NOT NULL,
    state           TEXT        NOT NULL,
    selected_skill  TEXT,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    routed_at       TIMESTAMPTZ,
    planned_at      TIMESTAMPTZ,
    context_built_at TIMESTAMPTZ,
    validated_at    TIMESTAMPTZ,
    executing_at    TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS runs_user_id_created_at_idx
    ON runs (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS runs_state_created_at_idx
    ON runs (state, created_at DESC);

-- ─────────────────────────────────────────────
-- route_decisions
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS route_decisions (
    decision_id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                  UUID        NOT NULL REFERENCES runs (run_id),
    skill_name              TEXT        NOT NULL,
    confidence              NUMERIC     NOT NULL,
    rationale               TEXT,
    requires_clarification  BOOL        NOT NULL DEFAULT FALSE,
    clarification_message   TEXT,
    candidate_skills        JSONB       NOT NULL DEFAULT '[]',
    prompt_version_id       TEXT,
    model_id                TEXT,
    decided_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS route_decisions_run_id_idx
    ON route_decisions (run_id);

-- ─────────────────────────────────────────────
-- plans
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS plans (
    plan_id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID        NOT NULL REFERENCES runs (run_id),
    skill_name          TEXT        NOT NULL,
    intent_summary      TEXT        NOT NULL,
    extracted_entities  JSONB       NOT NULL DEFAULT '{}',
    prompt_version_id   TEXT,
    model_id            TEXT,
    planned_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS plans_run_id_idx
    ON plans (run_id);

-- ─────────────────────────────────────────────
-- context_packs
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS context_packs (
    pack_id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                  UUID        NOT NULL REFERENCES runs (run_id),
    plan_id                 UUID        NOT NULL REFERENCES plans (plan_id),
    skill_name              TEXT        NOT NULL,
    sources                 JSONB       NOT NULL DEFAULT '[]',
    unresolved_ambiguities  JSONB       NOT NULL DEFAULT '[]',
    token_estimate          INT         NOT NULL,
    artifact_key            TEXT,
    built_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS context_packs_run_id_idx
    ON context_packs (run_id);

-- ─────────────────────────────────────────────
-- validation_results
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS validation_results (
    result_id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID        NOT NULL REFERENCES runs (run_id),
    plan_id             UUID        NOT NULL REFERENCES plans (plan_id),
    passed              BOOL        NOT NULL,
    checks              JSONB       NOT NULL DEFAULT '[]',
    risk_level          TEXT        NOT NULL,
    requires_approval   BOOL        NOT NULL DEFAULT FALSE,
    validated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────
-- execution_results
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS execution_results (
    result_id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID        NOT NULL REFERENCES runs (run_id),
    plan_id             UUID        NOT NULL REFERENCES plans (plan_id),
    success             BOOL        NOT NULL,
    output              JSONB       NOT NULL DEFAULT '{}',
    formatted_response  TEXT,
    artifacts           JSONB       NOT NULL DEFAULT '[]',
    llm_call_ids        JSONB       NOT NULL DEFAULT '[]',
    executed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────
-- feedback
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID        NOT NULL REFERENCES runs (run_id),
    user_id             TEXT        NOT NULL,
    helpful             BOOL,
    score               SMALLINT,
    comment             TEXT,
    failure_reason      TEXT,
    implicit_signals    JSONB       NOT NULL DEFAULT '[]',
    captured_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS feedback_run_id_idx
    ON feedback (run_id);

-- ─────────────────────────────────────────────
-- token_cost_records
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS token_cost_records (
    record_id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID        REFERENCES runs (run_id),
    skill_name          TEXT,
    stage               TEXT        NOT NULL,
    provider            TEXT        NOT NULL,
    model_id            TEXT        NOT NULL,
    prompt_tokens       INT         NOT NULL,
    completion_tokens   INT         NOT NULL,
    total_tokens        INT         NOT NULL,
    estimated_cost_usd  NUMERIC     NOT NULL,
    latency_ms          INT         NOT NULL,
    error               TEXT,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS token_cost_records_run_id_stage_idx
    ON token_cost_records (run_id, stage);

-- ─────────────────────────────────────────────
-- evaluation_cases
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS evaluation_cases (
    case_id                     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_run_id               UUID,
    request_text                TEXT        NOT NULL,
    expected_skill              TEXT,
    expected_asset_refs         JSONB       NOT NULL DEFAULT '[]',
    observed_skill              TEXT,
    observed_response           TEXT,
    feedback_score              SMALLINT,
    feedback_failure_reason     TEXT,
    human_label                 TEXT,
    dataset_tags                JSONB       NOT NULL DEFAULT '[]',
    status                      TEXT        NOT NULL,
    created_by                  TEXT        NOT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS evaluation_cases_status_created_at_idx
    ON evaluation_cases (status, created_at DESC);

-- ─────────────────────────────────────────────
-- prompt_versions
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prompt_versions (
    version_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    component       TEXT        NOT NULL,
    version_hash    TEXT        NOT NULL,
    content         TEXT        NOT NULL,
    model_id        TEXT        NOT NULL,
    is_active       BOOL        NOT NULL DEFAULT FALSE,
    deployed_at     TIMESTAMPTZ,
    created_by      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS prompt_versions_component_hash_idx
    ON prompt_versions (component, version_hash);

-- ─────────────────────────────────────────────
-- business_docs  (full-text search)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS business_docs (
    doc_id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_type        TEXT        NOT NULL,   -- 'kpi_glossary' | 'business_logic' | 'caveat'
    title           TEXT        NOT NULL,
    content         TEXT        NOT NULL,
    search_vector   TSVECTOR    GENERATED ALWAYS AS (
                        to_tsvector('english', title || ' ' || content)
                    ) STORED,
    owner           TEXT,
    source_path     TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS business_docs_search_idx
    ON business_docs USING GIN (search_vector);
