from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="openai:gpt-5.4-mini", alias="OPENAI_MODEL")
    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    sec_user_agent: str = Field(
        default="investment-coach-bot/0.1 contact@example.com",
        alias="SEC_USER_AGENT",
    )
    http_timeout_seconds: float = Field(default=10.0, alias="HTTP_TIMEOUT_SECONDS")


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    return Settings()
