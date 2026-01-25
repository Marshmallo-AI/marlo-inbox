from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.google_oauth import SESSION_KEY_USER

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/profile")
async def get_profile(request: Request) -> JSONResponse:
    """
    Get the current user's profile from session.
    """
    user = request.session.get(SESSION_KEY_USER)

    if user is None:
        return JSONResponse({"user": None}, status_code=200)

    return JSONResponse(
        {
            "user": {
                "sub": user.get("sub"),
                "name": user.get("name"),
                "email": user.get("email"),
                "picture": user.get("picture"),
            }
        }
    )
