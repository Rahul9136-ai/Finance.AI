from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI-ERP-Finance"
    env: str = "dev"
    secret_key: str = "dev-secret-change-me-please-min-32-characters"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Empty => SQLite dev default
    database_url: str = ""

    # AI
    ai_provider: str = "auto"  # auto | openai | anthropic | ollama | rules
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    ai_model_openai: str = "gpt-4o-mini"
    ai_model_anthropic: str = "claude-sonnet-5"
    ollama_base_url: str = "http://localhost:11434"
    ai_model_ollama: str = "llama3.2"

    cors_origins: str = "http://localhost:3000"

    @property
    def sqlalchemy_url(self) -> str:
        return self.database_url or "sqlite:///./erp.db"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
