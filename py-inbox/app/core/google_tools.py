from __future__ import annotations

import logging
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable

from langgraph.types import interrupt

logger = logging.getLogger(__name__)

_google_access_token: ContextVar[str | None] = ContextVar("google_access_token", default=None)


def set_google_access_token(token: str | None) -> None:
    """Set the Google access token for the current context."""
    _google_access_token.set(token)


def get_google_access_token() -> str | None:
    """Get the Google access token from the current context."""
    return _google_access_token.get()


class GoogleAuthInterrupt(Exception):
    """Exception raised when Google authentication is required."""

    def __init__(self, message: str = "Google authentication required"):
        self.message = message
        super().__init__(message)


def require_google_auth(tool_func: Callable) -> Callable:
    """
    Decorator for tools that require Google authentication.

    If no access token is available, triggers a LangGraph interrupt
    to request authentication from the user.
    """

    @wraps(tool_func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        access_token = get_google_access_token()
        logger.info(f"[require_google_auth] Tool {tool_func.__name__} - access_token exists: {bool(access_token)}")

        if not access_token:
            logger.info("No Google access token available, triggering interrupt")
            return interrupt({
                "type": "google_auth_required",
                "message": "Please connect your Google account to access Gmail and Calendar.",
                "action": "authorize",
            })

        return await tool_func(*args, **kwargs)

    return wrapper


def get_gmail_service():
    """Get Gmail service with current access token."""
    from app.services.gmail import GmailService

    access_token = get_google_access_token()
    if not access_token:
        raise GoogleAuthInterrupt("Google authentication required for Gmail access")

    return GmailService(access_token)


def get_calendar_service():
    """Get Calendar service with current access token."""
    from app.services.calendar import CalendarService

    access_token = get_google_access_token()
    if not access_token:
        raise GoogleAuthInterrupt("Google authentication required for Calendar access")

    return CalendarService(access_token)
