from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.core.config import settings
from app.core.google_oauth import get_valid_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

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
        logger.info("[agent proxy] Access token refreshed successfully")
        if request is not None:
            request.session[SESSION_KEY_TOKENS] = updated_tokens
            tokens = updated_tokens
        access_token = updated_tokens.get("access_token")
    elif access_token is None:
        logger.warning("[agent proxy] Failed to get valid access token - may need to re-authenticate")

    return {
        "access_token": access_token,
        "refresh_token": tokens.get("refresh_token"),
        "user": user,
    }


def _inject_credentials_into_body(body: dict[str, Any], credentials: dict[str, Any]) -> dict[str, Any]:
    """Inject credentials into the request body's config."""
    if "config" not in body:
        body["config"] = {}
    if "configurable" not in body["config"]:
        body["config"]["configurable"] = {}

    body["config"]["configurable"]["_credentials"] = credentials
    return body


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_to_langgraph(request: Request, path: str):
    """
    Proxy all agent requests to LangGraph server with credentials injected.
    """
    target_url = f"{settings.LANGGRAPH_API_URL}/{path}"

    if request.query_params:
        target_url += f"?{request.query_params}"

    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    credentials = {}
    session_dict = dict(request.session)
    logger.info(f"[agent proxy] Session keys: {list(session_dict.keys())}")

    if SESSION_KEY_USER in session_dict:
        credentials = _get_credentials_from_session(session_dict, request)
        has_token = bool(credentials.get("access_token"))
        logger.info(f"[agent proxy] User: {credentials.get('user', {}).get('email', 'unknown')}, has_token: {has_token}")
    else:
        logger.warning("[agent proxy] No user in session - credentials will be empty")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            body = None
            json_body = None

            if request.method in ["POST", "PUT", "PATCH"]:
                try:
                    body = await request.json()
                    body = _inject_credentials_into_body(body, credentials)
                    json_body = body
                    body = None
                except Exception:
                    body = await request.body()

            is_sse = request.headers.get("accept") == "text/event-stream"

            if is_sse:
                async def stream_response():
                    async with client.stream(
                        request.method,
                        target_url,
                        json=json_body,
                        content=body,
                        headers=headers,
                    ) as response:
                        async for chunk in response.aiter_bytes():
                            yield chunk

                return StreamingResponse(
                    stream_response(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
                )
            else:
                response = await client.request(
                    request.method,
                    target_url,
                    json=json_body,
                    content=body,
                    headers=headers,
                )

                response_headers = dict(response.headers)
                response_headers.pop("content-encoding", None)
                response_headers.pop("transfer-encoding", None)

                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=response_headers,
                    media_type=response.headers.get("content-type"),
                )

    except httpx.ConnectError as e:
        logger.error(f"Failed to connect to LangGraph server: {e}")
        return JSONResponse(
            {"error": "LangGraph server not available"},
            status_code=503,
        )
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        return JSONResponse(
            {"error": str(e)},
            status_code=500,
        )
