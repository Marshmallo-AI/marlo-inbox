from __future__ import annotations

import logging

from auth0_ai.authorizers.async_authorizer import AsyncAuthorizer
from auth0_ai.authorizers.sync_authorizer import SyncAuthorizer
from auth0_ai_langchain.auth0_ai import Auth0AI

from app.core.config import settings

logger = logging.getLogger(__name__)

auth0_ai = Auth0AI()

GOOGLE_CONNECTION_NAME = "google-oauth2"

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

GOOGLE_CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


def get_token_vault():
    """Get Auth0 token vault for federated connections (Google)."""
    return auth0_ai.get_token_vault(
        domain=settings.AUTH0_DOMAIN,
        client_id=settings.AUTH0_CLIENT_ID,
        client_secret=settings.AUTH0_CLIENT_SECRET,
    )


def with_google_access(tool):
    """Decorator to inject Google access token into tool via Auth0 Token Vault."""
    token_vault = get_token_vault()

    return auth0_ai.with_token_for_connection(
        tool=tool,
        connection=GOOGLE_CONNECTION_NAME,
        scopes=GOOGLE_SCOPES,
        token_vault=token_vault,
    )


def with_calendar_access(tool):
    """Decorator to inject Google Calendar access token via Auth0 Token Vault."""
    token_vault = get_token_vault()

    return auth0_ai.with_token_for_connection(
        tool=tool,
        connection=GOOGLE_CONNECTION_NAME,
        scopes=GOOGLE_CALENDAR_SCOPES,
        token_vault=token_vault,
    )


def with_gmail_access(tool):
    """Decorator to inject Gmail access token into tool via Auth0 Token Vault."""
    return with_google_access(tool)


def get_async_authorizer() -> AsyncAuthorizer:
    """Get async authorizer for tools requiring user confirmation."""
    return auth0_ai.get_async_authorizer(
        domain=settings.AUTH0_DOMAIN,
        client_id=settings.AUTH0_CLIENT_ID,
        client_secret=settings.AUTH0_CLIENT_SECRET,
    )


def get_sync_authorizer() -> SyncAuthorizer:
    """Get sync authorizer for tools requiring user confirmation."""
    return auth0_ai.get_sync_authorizer(
        domain=settings.AUTH0_DOMAIN,
        client_id=settings.AUTH0_CLIENT_ID,
        client_secret=settings.AUTH0_CLIENT_SECRET,
    )
