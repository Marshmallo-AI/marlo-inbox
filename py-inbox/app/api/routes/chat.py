from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.google_oauth import get_valid_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

SESSION_KEY_TOKENS = "google_tokens"
SESSION_KEY_USER = "user"


def _get_credentials_from_session(session: dict[str, Any], request: Request | None = None) -> dict[str, Any]:
    """Extract Google credentials from session for agent config, refreshing if expired."""
    tokens = session.get(SESSION_KEY_TOKENS, {})
    user = session.get(SESSION_KEY_USER, {})

    if not tokens:
        return {"access_token": None, "refresh_token": None, "user": user}

    # Check if token needs refresh and refresh if needed
    access_token, updated_tokens = get_valid_access_token(tokens)

    if updated_tokens:
        # Token was refreshed - update session with new tokens
        logger.info("[chat] Access token refreshed successfully")
        if request is not None:
            request.session[SESSION_KEY_TOKENS] = updated_tokens
            tokens = updated_tokens
        access_token = updated_tokens.get("access_token")
    elif access_token is None:
        logger.warning("[chat] Failed to get valid access token - may need to re-authenticate")

    return {
        "access_token": access_token,
        "refresh_token": tokens.get("refresh_token"),
        "user": user,
    }


@router.post("/stream")
async def stream_chat(request: Request):
    """
    Stream chat messages to the LangGraph agent.
    Proxies requests to the LangGraph server with injected credentials.
    """
    if SESSION_KEY_USER not in request.session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    thread_id = body.get("thread_id")
    messages = body.get("messages", [])

    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    credentials = _get_credentials_from_session(dict(request.session), request)

    if not credentials.get("access_token"):
        logger.warning("[chat] No valid access token - user must re-authenticate")
        raise HTTPException(
            status_code=401,
            detail="Google authentication expired. Please log in again.",
        )

    langgraph_payload = {
        "input": {"messages": messages},
        "config": {
            "configurable": {
                "_credentials": credentials,
                "thread_id": thread_id,
            }
        },
        "stream_mode": ["messages", "updates"],
    }

    async def stream_response():
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{settings.LANGGRAPH_API_URL}/runs/stream",
                json=langgraph_payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
    )


@router.post("/invoke")
async def invoke_chat(request: Request):
    """
    Invoke chat without streaming.
    Returns complete response after agent finishes.
    """
    if SESSION_KEY_USER not in request.session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    thread_id = body.get("thread_id")
    messages = body.get("messages", [])

    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    credentials = _get_credentials_from_session(dict(request.session), request)

    if not credentials.get("access_token"):
        logger.warning("[chat] No valid access token - user must re-authenticate")
        raise HTTPException(
            status_code=401,
            detail="Google authentication expired. Please log in again.",
        )

    langgraph_payload = {
        "input": {"messages": messages},
        "config": {
            "configurable": {
                "_credentials": credentials,
                "thread_id": thread_id,
            }
        },
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.LANGGRAPH_API_URL}/runs/wait",
            json=langgraph_payload,
            headers={"Content-Type": "application/json"},
        )

        if response.status_code != 200:
            logger.error(f"LangGraph error: {response.text}")
            raise HTTPException(status_code=502, detail="Agent error")

        return response.json()
