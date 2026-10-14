from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"

# Third-party libs (pydantic-ai's AnthropicProvider, boto3, logfire) read straight from
# os.environ rather than through our Settings object below — load the same root .env
# into the real environment so both agree on one source of truth.
load_dotenv(REPO_ROOT_ENV)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT_ENV, extra="ignore")

    # Whichever provider AGENT_MODEL names needs its key; pydantic-ai reads it from the env.
    openrouter_api_key: str = ""
    anthropic_api_key: str = ""
    # NVIDIA's hosted API (build.nvidia.com): "nvidia:<model id>" in AGENT_MODEL. Free tier
    # is rate-limited (~40 requests/min reported), not capped per day.
    nvidia_api_key: str = ""
    logfire_token: str = ""

    database_url: str = ""
    database_url_unpooled: str = ""
    neon_branch: str = ""

    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_endpoint_url_s3: str = ""
    aws_region: str = ""
    object_storage_bucket: str = "ryde-resolve"

    # The five agents; must support tool calling. pydantic-ai "<provider>:<model>" form,
    # e.g. "anthropic:claude-haiku-5-5". OpenRouter ":free" models allow 20 requests/min
    # and 50/day (1000/day once the account has bought $10 of credits); one case makes
    # roughly 10-20 requests, and free models' shared upstream pools get rate-limited.
    agent_model: str = "openrouter:nvidia/nemotron-3-super-120b-a12b:free"
    # Comma-separated models tried in order when the main one errors. For OpenRouter, bare
    # slugs (OpenRouter falls back server-side); for any other provider, full
    # "<provider>:<model>" strings (pydantic-ai's FallbackModel), e.g. Gemini's free tier
    # allows 5 requests/min per model, so "google:gemini-3.8-flash,google:gemini-3.5-flash-lite"
    # spreads a case across three quotas.
    agent_fallback_models: str = (
        "google/gemma-4-31b-it:free,nvidia/nemotron-3-ultra-550b-a55b:free"
    )
    # Image Analysis: same form, but every model in its chain must accept images.
    vision_model: str = "openrouter:google/gemma-4-31b-it:free"
    vision_fallback_models: str = (
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free,google/gemma-4-26b-a4b-it:free"
    )
    # How agents return their typed result: "tool" (a final_result tool call, pydantic-ai's
    # default and best for Anthropic models), "native" (schema-constrained JSON, only on
    # models pydantic-ai knows support it) or "prompted" (JSON in plain text, validated).
    # The free OpenRouter models mangle the final_result tool call, so "prompted".
    agent_output_mode: str = "prompted"
    # Image Analysis's own output mode; empty means the same as AGENT_OUTPUT_MODE. Lets the
    # vision model sit on a different provider (e.g. OpenRouter's free Gemma for photos
    # while the agents run on NVIDIA, whose hosted vision models time out on images).
    vision_output_mode: str = ""
    # Thinking counts toward this cap on current Claude models, so keep headroom.
    agent_max_tokens: int = 16000
    # Anthropic models only: low | medium | high | xhigh | max. Ignored for others.
    agent_effort: str | None = "medium"
    # Claude Haiku 5.5 and Opus 5.5 reject any non-default sampling value with a 400:
    # leave unset for them, set it only for models that accept it.
    agent_temperature: float | None = None

    # Comma-separated allowed origins for the browser frontend. "*" is fine for the demo:
    # the API uses no cookies or credentials. Set it to the Vercel URL to lock it down.
    cors_origins: str = "*"

    onemap_access_token: str = ""
    # Optional: if set, the OneMap client self-refreshes an expired token via OneMap's
    # auth endpoint instead of relying on the static token above, which expires every
    # ~3 days (data sources doc §5) — a manually pasted token WILL go stale mid-build.
    onemap_email: str = ""
    onemap_password: str = ""


settings = Settings()
