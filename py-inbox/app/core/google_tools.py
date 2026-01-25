from __future__ import annotations

import logging
from contextvars import ContextVar

logger = logging.getLogger(__name__)

_google_access_token: ContextVar[str | None] = ContextVar("google_access_token", default=None)


def set_google_access_token(token: str | None) -> None:
    """Set the Google access token for the current context."""
    _google_access_token.set(token)


def get_google_access_token() -> str | None:
    """Get the Google access token from the current context."""
    return _google_access_token.get()


class GoogleAuthError(Exception):
    """Exception raised when Google authentication is missing or invalid."""

    def __init__(self, message: str = "Google authentication required"):
        self.message = message
        super().__init__(message)


def get_gmail_service():
    """Get Gmail service with current access token."""
    from app.services.gmail import GmailService

    access_token = get_google_access_token()
    if not access_token:
        raise GoogleAuthError("Not authenticated. Please log in first.")

    return GmailService(access_token)


def get_calendar_service():
    """Get Calendar service with current access token."""
    from app.services.calendar import CalendarService

    access_token = get_google_access_token()
    if not access_token:
        raise GoogleAuthError("Not authenticated. Please log in first.")

    return CalendarService(access_token)
