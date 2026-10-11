-- Initial schema: system design §5 tables + data sources §3 tables.
-- Applied against Neon Postgres (pgvector extension already available on Neon).

CREATE EXTENSION IF NOT EXISTS vector;

-- `cases`, `evidence`, and `chat_messages` use app-generated TEXT business-key IDs
-- (CASE-0001, EV-0001, MSG-0001), not UUIDs — these three are the only tables whose IDs
-- get cited directly by name (Argument.cites, DecisionObject.case_id, the trace panel),
-- and every hand-written fixture on both sides already uses this convention. Everything
-- else (users, trips, payments, ...) stays UUID since nothing cites those IDs directly.
CREATE SEQUENCE case_id_seq;
CREATE SEQUENCE evidence_id_seq;
CREATE SEQUENCE chat_message_id_seq;

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role TEXT NOT NULL CHECK (role IN ('rider', 'driver')),
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    rating NUMERIC(3, 2),
    rating_trend NUMERIC(4, 3)
);

CREATE TABLE trips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rider_id UUID NOT NULL REFERENCES users(id),
    driver_id UUID NOT NULL REFERENCES users(id),
    pickup_lat DOUBLE PRECISION NOT NULL,
    pickup_lng DOUBLE PRECISION NOT NULL,
    dropoff_lat DOUBLE PRECISION NOT NULL,
    dropoff_lng DOUBLE PRECISION NOT NULL,
    optimal_route_geometry JSONB,
    actual_route_geometry JSONB,
    gps_trace JSONB,
    scheduled_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    -- generation-time label only; never visible to any agent (data sources §3)
    category_hint TEXT
);

CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID NOT NULL REFERENCES trips(id),
    base_fare NUMERIC(10, 2) NOT NULL,
    platform_fee NUMERIC(10, 2) NOT NULL,
    taxes NUMERIC(10, 2) NOT NULL,
    total_fare NUMERIC(10, 2) NOT NULL,
    add_on_fees JSONB DEFAULT '[]',
    payment_method TEXT
);

CREATE TABLE chat_messages (
    id TEXT PRIMARY KEY DEFAULT ('MSG-' || lpad(nextval('chat_message_id_seq')::text, 4, '0')),
    trip_id UUID NOT NULL REFERENCES trips(id),
    sender_role TEXT NOT NULL CHECK (sender_role IN ('rider', 'driver')),
    timestamp TIMESTAMPTZ NOT NULL,
    text TEXT NOT NULL
);

CREATE TABLE traffic_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    near_lat DOUBLE PRECISION NOT NULL,
    near_lng DOUBLE PRECISION NOT NULL,
    time_window_start TIMESTAMPTZ NOT NULL,
    time_window_end TIMESTAMPTZ NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('road_closure', 'accident', 'construction')),
    description TEXT
);

CREATE TABLE behavior_profiles (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    dispute_count_30d INT NOT NULL DEFAULT 0,
    upheld_count INT NOT NULL DEFAULT 0,
    denied_count INT NOT NULL DEFAULT 0,
    rating_trend NUMERIC(4, 3),
    account_age_days INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE cases (
    id TEXT PRIMARY KEY DEFAULT ('CASE-' || lpad(nextval('case_id_seq')::text, 4, '0')),
    trip_id UUID NOT NULL REFERENCES trips(id),
    complainer_id UUID NOT NULL REFERENCES users(id),
    complainee_id UUID NOT NULL REFERENCES users(id),
    category TEXT,
    tier TEXT,
    state TEXT NOT NULL DEFAULT 'opened',
    is_safety BOOLEAN NOT NULL DEFAULT false,
    -- the complainer's own words; given to the advocates, never to the Judge (§4 rule 2)
    claim_text TEXT,
    -- the canonical CaseFile the Evidence Collection Agent assembled, so adjudication
    -- (triggered later by the response) runs on exactly what was assembled
    case_file JSONB,
    response_deadline TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE evidence (
    id TEXT PRIMARY KEY DEFAULT ('EV-' || lpad(nextval('evidence_id_seq')::text, 4, '0')),
    case_id TEXT NOT NULL REFERENCES cases(id),
    kind TEXT NOT NULL,
    hash TEXT NOT NULL,
    object_key TEXT NOT NULL,  -- Neon Object Storage (ryde-resolve bucket) key
    submitted_by UUID REFERENCES users(id),
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id TEXT NOT NULL REFERENCES cases(id),
    respondent_id UUID NOT NULL REFERENCES users(id),
    text TEXT,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id TEXT NOT NULL REFERENCES cases(id),
    outcome TEXT NOT NULL,
    remedy JSONB NOT NULL,
    reasoning JSONB NOT NULL,
    policy_applied TEXT,
    confidence NUMERIC(4, 3) NOT NULL,
    escalation JSONB NOT NULL,
    human_ratified BOOLEAN NOT NULL DEFAULT false,
    ratified_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE trace_events (
    id BIGSERIAL PRIMARY KEY,
    case_id TEXT REFERENCES cases(id),
    t TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind TEXT NOT NULL,
    agent TEXT,
    detail TEXT,
    latency_ms INT,
    output JSONB
);

CREATE TABLE golden_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- labeled against a trip, not a case: a golden case has no real `cases` row until
    -- /golden-run actually files a claim for it (data sources §4 step 11) and compares
    -- the result to expected_outcome; case_id is populated by that run, not at label time.
    trip_id UUID NOT NULL REFERENCES trips(id),
    case_id TEXT REFERENCES cases(id),
    expected_outcome JSONB NOT NULL,
    -- {kind, hash, object_key} evidence already uploaded to Object Storage at label
    -- time (Property Damage only) — pass straight through to POST /cases' `evidence`
    -- field when a golden run actually files this claim.
    prepared_evidence JSONB NOT NULL DEFAULT '[]',
    last_run_result JSONB,
    last_run_at TIMESTAMPTZ
);

CREATE TABLE policy_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id TEXT NOT NULL,
    heading TEXT NOT NULL,
    text TEXT NOT NULL,
    source TEXT,
    embedding VECTOR(1536)
);

CREATE INDEX idx_trips_category_hint ON trips (category_hint);
CREATE INDEX idx_cases_state ON cases (state);
CREATE INDEX idx_trace_events_case_id ON trace_events (case_id);
CREATE INDEX idx_evidence_case_id ON evidence (case_id);
