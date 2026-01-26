from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.core.config import settings

logger = logging.getLogger(__name__)

GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

SESSION_KEY_TOKENS = "google_tokens"
SESSION_KEY_USER = "user"


def _create_flow(state: str | None = None) -> Flow:
    """Create a Google OAuth flow."""
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=GOOGLE_SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )

    if state:
        flow.state = state

    return flow


def get_authorization_url(return_to: str | None = None) -> tuple[str, str]:
    """
    Generate Google OAuth authorization URL.

    Returns:
        Tuple of (authorization_url, state)
    """
    flow = _create_flow()

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=return_to or "/",
    )

    return authorization_url, state


def exchange_code_for_tokens(code: str, state: str | None = None) -> dict[str, Any]:
    """
    Exchange authorization code for tokens.

    Returns:
        Token data dict with access_token, refresh_token, expiry, etc.
    """
    flow = _create_flow(state=state)
    flow.fetch_token(code=code)

    credentials = flow.credentials

    token_data = {
        "access_token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes) if credentials.scopes else GOOGLE_SCOPES,
    }

    if credentials.expiry:
        token_data["expiry"] = credentials.expiry.isoformat()

    return token_data


def get_credentials_from_tokens(token_data: dict[str, Any]) -> Credentials | None:
    """
    Create Credentials object from stored token data.

    Returns:
        Google Credentials object or None if invalid
    """
    if not token_data or not token_data.get("access_token"):
        return None

    expiry = None
    if token_data.get("expiry"):
        try:
            expiry = datetime.fromisoformat(token_data["expiry"])
            # Google auth library uses naive datetimes internally (UTC assumed)
            # Remove timezone info to avoid comparison errors
            if expiry.tzinfo is not None:
                expiry = expiry.replace(tzinfo=None)
        except (ValueError, TypeError):
            pass

    return Credentials(
        token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id", settings.GOOGLE_CLIENT_ID),
        client_secret=token_data.get("client_secret", settings.GOOGLE_CLIENT_SECRET),
        scopes=token_data.get("scopes", GOOGLE_SCOPES),
        expiry=expiry,
    )


def refresh_credentials(credentials: Credentials) -> dict[str, Any] | None:
    """
    Refresh credentials if expired.

    Returns:
        Updated token data if refreshed, None if refresh failed
    """
    from google.auth.transport.requests import Request

    if not credentials.expired or not credentials.refresh_token:
        return None

    try:
        credentials.refresh(Request())

        return {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes) if credentials.scopes else GOOGLE_SCOPES,
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        }
    except Exception as e:
        logger.warning(f"Failed to refresh credentials: {e}")
        return None


def _is_token_expired(token_data: dict[str, Any]) -> bool:
    """Check if token is expired, handling timezone issues safely."""
    expiry_str = token_data.get("expiry")
    if not expiry_str:
        # No expiry info - assume not expired, let the API call fail if it is
        return False

    try:
        expiry = datetime.fromisoformat(expiry_str)
        # Ensure both datetimes are timezone-aware for comparison
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        # Add a small buffer (5 minutes) to refresh before actual expiry
        return now >= expiry - timedelta(minutes=5)
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse token expiry: {e}")
        return False


def get_valid_access_token(token_data: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    """
    Get a valid access token, refreshing if needed.

    Returns:
        Tuple of (access_token, updated_token_data)
        - access_token: Valid access token or None
        - updated_token_data: New token data if refreshed, None otherwise
    """
    if not token_data or not token_data.get("access_token"):
        logger.debug("[oauth] No token data or access token")
        return None, None

    # Check if token is expired
    if _is_token_expired(token_data):
        logger.info("[oauth] Token expired, attempting refresh")
        if token_data.get("refresh_token"):
            credentials = get_credentials_from_tokens(token_data)
            if credentials:
                updated = refresh_credentials(credentials)
                if updated:
                    logger.info("[oauth] Token refreshed successfully")
                    return updated["access_token"], updated
            logger.warning("[oauth] Token refresh failed")
            return None, None
        else:
            logger.warning("[oauth] Token expired and no refresh token - user must re-authenticate")
            return None, None

    return token_data.get("access_token"), None


async def get_user_info(access_token: str) -> dict[str, Any] | None:
    """
    Fetch user info from Google using access token.
    """
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch user info: {e}")

    return None
