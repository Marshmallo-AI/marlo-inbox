from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.auth import auth_client
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


def _get_credentials_from_session(session: dict[str, Any]) -> dict[str, Any]:
    """Extract credentials from Auth0 session for agent config."""
    token_sets = session.get("token_sets", [])
    access_token = token_sets[0].get("access_token") if token_sets else None
    refresh_token = session.get("refresh_token")
    user = session.get("user", {})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user,
    }


@router.post("/stream")
async def stream_chat(request: Request):
    """
    Stream chat messages to the LangGraph agent.
    Proxies requests to the LangGraph server with injected credentials.
    """
    session = await auth_client.get_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    thread_id = body.get("thread_id")
    messages = body.get("messages", [])

    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    credentials = _get_credentials_from_session(session)

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
    session = await auth_client.get_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    thread_id = body.get("thread_id")
    messages = body.get("messages", [])

    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    credentials = _get_credentials_from_session(session)

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
