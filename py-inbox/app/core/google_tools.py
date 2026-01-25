from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)


class GoogleAuthError(Exception):
    """Exception raised when Google authentication is missing or invalid."""

    def __init__(self, message: str = "Google authentication required"):
        self.message = message
        super().__init__(message)


def get_access_token_from_config(config: RunnableConfig | None) -> str | None:
    """Extract Google access token from RunnableConfig."""
    if not config:
        logger.warning("[google_tools] No config provided")
        return None

    configurable = config.get("configurable", {})
    credentials = configurable.get("_credentials", {})
    access_token = credentials.get("access_token") if isinstance(credentials, dict) else None

    if access_token:
        logger.debug(f"[google_tools] Access token found (length: {len(access_token)})")
    else:
        logger.warning("[google_tools] No access token in config")

    return access_token
