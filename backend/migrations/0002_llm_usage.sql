-- One row per model call: every pydantic-ai agent run and every Image Analysis vision
-- call. Tokens as reported by the provider (Groq). No cost column on purpose: cost is
-- tokens × the provider's price, which changes; compute it at query time.
-- case_id has no foreign key so usage history survives case cleanup (a golden run
-- deletes its previous cases, but the tokens were really spent).
CREATE TABLE IF NOT EXISTS llm_usage (
    id BIGSERIAL PRIMARY KEY,
    case_id TEXT,
    agent TEXT NOT NULL,            -- triage, evidence_collection, rider_advocate, ..., image_analysis
    model TEXT NOT NULL,
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    requests INT NOT NULL DEFAULT 1,    -- model round-trips in the run (tool calls, retries)
    tool_calls INT NOT NULL DEFAULT 0,
    latency_ms INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_case_id ON llm_usage (case_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_created_at ON llm_usage (created_at);
