from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.core.auth import auth_client
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    """Redirect user to Auth0 login page."""
    return await auth_client.login(request)


@router.get("/callback")
async def callback(request: Request):
    """Handle Auth0 callback after successful authentication."""
    await auth_client.callback(request)
    return RedirectResponse(url=settings.APP_BASE_URL)


@router.get("/logout")
async def logout(request: Request):
    """Log user out and redirect to home."""
    return await auth_client.logout(
        request,
        return_to=settings.auth0_logout_redirect,
    )


@router.get("/me")
async def get_current_user(request: Request):
    """Get current authenticated user info."""
    session = await auth_client.get_session(request)
    if not session:
        return {"authenticated": False}

    return {
        "authenticated": True,
        "user": session.get("user"),
    }
