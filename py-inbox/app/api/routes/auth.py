from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.google_oauth import (
    SESSION_KEY_TOKENS,
    SESSION_KEY_USER,
    exchange_code_for_tokens,
    get_authorization_url,
    get_user_info,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request, returnTo: str | None = None):
    """
    Initiate Google OAuth login flow.
    """
    return_to = returnTo or request.query_params.get("returnTo", "/")
    authorization_url, state = get_authorization_url(return_to)

    request.session["oauth_state"] = state

    return RedirectResponse(url=authorization_url)


@router.get("/callback")
async def callback(request: Request):
    """
    Handle Google OAuth callback.
    """
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        logger.error(f"OAuth error: {error}")
        return RedirectResponse(url=f"{settings.APP_BASE_URL}?error={error}")

    if not code:
        logger.error("No authorization code received")
        return RedirectResponse(url=f"{settings.APP_BASE_URL}?error=no_code")

    try:
        token_data = exchange_code_for_tokens(code, state)

        request.session[SESSION_KEY_TOKENS] = token_data

        user_info = await get_user_info(token_data["access_token"])
        if user_info:
            request.session[SESSION_KEY_USER] = {
                "sub": user_info.get("id"),
                "email": user_info.get("email"),
                "name": user_info.get("name"),
                "picture": user_info.get("picture"),
            }

        return_to = state if state and state.startswith("/") else "/"
        return RedirectResponse(url=f"{settings.APP_BASE_URL}{return_to}")

    except Exception as e:
        logger.exception(f"OAuth callback error: {e}")
        error_params = urlencode({"error": "auth_failed", "message": str(e)})
        return RedirectResponse(url=f"{settings.APP_BASE_URL}?{error_params}")


@router.get("/logout")
async def logout(request: Request, returnTo: str | None = None):
    """
    Log out the user by clearing the session.
    """
    request.session.clear()

    return_to = returnTo or request.query_params.get("returnTo", settings.APP_BASE_URL)

    return RedirectResponse(url=return_to)


@router.get("/status")
async def auth_status(request: Request):
    """
    Check if user is authenticated and has valid tokens.
    """
    tokens = request.session.get(SESSION_KEY_TOKENS)
    user = request.session.get(SESSION_KEY_USER)

    return {
        "authenticated": bool(tokens and tokens.get("access_token")),
        "has_google_tokens": bool(tokens and tokens.get("access_token")),
        "user": user,
    }
