from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"

# Third-party libs (pydantic-ai's GroqProvider, boto3, logfire) read straight from
# os.environ rather than through our Settings object below — load the same root .env
# into the real environment so both agree on one source of truth.
load_dotenv(REPO_ROOT_ENV)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT_ENV, extra="ignore")

    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    logfire_token: str = ""

    database_url: str = ""
    database_url_unpooled: str = ""
    neon_branch: str = ""

    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_endpoint_url_s3: str = ""
    aws_region: str = ""
    object_storage_bucket: str = "ryde-resolve"

    agent_model: str = "groq:qwen/qwen3.8-27b"


settings = Settings()
