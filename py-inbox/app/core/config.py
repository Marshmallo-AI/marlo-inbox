from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_NAME: str = "marlo-inbox"
    APP_BASE_URL: str = "http://localhost:5173"
    API_PREFIX: str = "/api"

    # Auth0
    AUTH0_DOMAIN: str
    AUTH0_CLIENT_ID: str
    AUTH0_CLIENT_SECRET: str
    AUTH0_SECRET: str
    AUTH0_AUDIENCE: str = ""

    # LLM
    OPENAI_API_KEY: str

    # LangGraph
    LANGGRAPH_API_URL: str = "http://localhost:54367"

    # Marlo
    MARLO_API_KEY: str = ""

    # LangSmith
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "marlo-inbox"

    @property
    def auth0_issuer(self) -> str:
        return f"https://{self.AUTH0_DOMAIN}/"

    @property
    def auth0_callback_url(self) -> str:
        return f"{self.APP_BASE_URL}{self.API_PREFIX}/auth/callback"

    @property
    def auth0_logout_redirect(self) -> str:
        return self.APP_BASE_URL


settings = Settings()
