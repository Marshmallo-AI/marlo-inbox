from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_NAME: str = "marlo-inbox"
    APP_BASE_URL: str = "http://localhost:5173"
    API_PREFIX: str = "/api"
    SESSION_SECRET: str = "change-me-in-production"

    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str

    # LLM
    OPENAI_API_KEY: str

    # LangGraph
    LANGGRAPH_API_URL: str = "http://localhost:2024"

    # Marlo
    MARLO_API_KEY: str

    # LangSmith
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "marlo-inbox"

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.APP_BASE_URL}{self.API_PREFIX}/auth/callback"


settings = Settings()
