from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import marlo
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.google_oauth import get_valid_access_token

logger = logging.getLogger(__name__)

AGENT_NAME = "inbox-pilot"
MODEL_NAME = "gpt-5"

router = APIRouter(prefix="/chat", tags=["chat"])

SESSION_KEY_TOKENS = "google_tokens"
SESSION_KEY_USER = "user"


def _get_credentials_from_session(session: dict[str, Any], request: Request | None = None) -> dict[str, Any]:
    """Extract Google credentials from session for agent config, refreshing if expired."""
    tokens = session.get(SESSION_KEY_TOKENS, {})
    user = session.get(SESSION_KEY_USER, {})

    if not tokens:
        return {"access_token": None, "refresh_token": None, "user": user}

    access_token, updated_tokens = get_valid_access_token(tokens)

    if updated_tokens:
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
    """Stream chat messages to the LangGraph agent."""
    if SESSION_KEY_USER not in request.session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    thread_id = body.get("thread_id")
    messages = body.get("messages", [])

    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    credentials = _get_credentials_from_session(dict(request.session), request)

    if not credentials.get("access_token"):
        raise HTTPException(status_code=401, detail="Google authentication expired. Please log in again.")

    user_message = messages[-1].get("content", "") if messages else ""

    with marlo.task(thread_id=thread_id, agent=AGENT_NAME) as task:
        task.input(user_message)

        # Fetch and inject learnings
        messages_to_send = list(messages)
        learnings = task.get_learnings()
        if learnings and learnings.get("learnings_text"):
            messages_to_send.insert(0, {"type": "system", "content": f"Learnings:\n{learnings['learnings_text']}"})

        langgraph_payload = {
            "input": {"messages": messages_to_send},
            "config": {"configurable": {"_credentials": credentials, "thread_id": thread_id}},
            "stream_mode": ["updates"],
        }

        async def stream_response():
            collected_messages: list[dict] = []

            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{settings.LANGGRAPH_API_URL}/runs/stream",
                    json=langgraph_payload,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk

                        try:
                            for line in chunk.decode("utf-8").split("\n"):
                                if line.startswith("data: "):
                                    data = json.loads(line[6:])
                                    if isinstance(data, dict):
                                        for node_data in data.values():
                                            if isinstance(node_data, dict) and "messages" in node_data:
                                                collected_messages.extend(node_data["messages"])
                        except Exception:
                            pass

            # Report events
            pending_tool_calls: dict[str, dict] = {}
            for msg in collected_messages:
                if msg.get("type") == "ai":
                    usage_metadata = msg.get("usage_metadata") or {}
                    usage = {
                        "prompt_tokens": usage_metadata.get("input_tokens", 0),
                        "completion_tokens": usage_metadata.get("output_tokens", 0),
                        "reasoning_tokens": usage_metadata.get("reasoning_tokens")
                            or usage_metadata.get("output_token_details", {}).get("reasoning_tokens", 0),
                    }
                    task.llm(model=MODEL_NAME, usage=usage, response=msg.get("content", ""))

                    additional_kwargs = msg.get("additional_kwargs", {})
                    reasoning = additional_kwargs.get("reasoning") or additional_kwargs.get("thinking") or ""
                    if reasoning:
                        task.reasoning(reasoning)

                    for tc in msg.get("tool_calls", []):
                        pending_tool_calls[tc.get("id", "")] = {"name": tc.get("name", ""), "input": tc.get("args", {})}

                elif msg.get("type") == "tool":
                    tool_info = pending_tool_calls.pop(msg.get("tool_call_id", ""), {})
                    task.tool(name=tool_info.get("name", "unknown"), input=tool_info.get("input", {}), output=msg.get("content", ""))

            for msg in reversed(collected_messages):
                if msg.get("type") == "ai" and msg.get("content"):
                    task.output(msg.get("content", ""))
                    break

        return StreamingResponse(stream_response(), media_type="text/event-stream")


@router.post("/invoke")
async def invoke_chat(request: Request):
    """Invoke chat without streaming."""
    if SESSION_KEY_USER not in request.session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    thread_id = body.get("thread_id")
    messages = body.get("messages", [])

    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    credentials = _get_credentials_from_session(dict(request.session), request)

    if not credentials.get("access_token"):
        raise HTTPException(status_code=401, detail="Google authentication expired. Please log in again.")

    user_message = messages[-1].get("content", "") if messages else ""

    with marlo.task(thread_id=thread_id, agent=AGENT_NAME) as task:
        task.input(user_message)

        # Fetch and inject learnings
        messages_to_send = list(messages)
        learnings = task.get_learnings()
        if learnings and learnings.get("learnings_text"):
            messages_to_send.insert(0, {"type": "system", "content": f"Learnings:\n{learnings['learnings_text']}"})

        langgraph_payload = {
            "input": {"messages": messages_to_send},
            "config": {"configurable": {"_credentials": credentials, "thread_id": thread_id}},
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

            result = response.json()

        result_messages = result.get("messages", [])
        pending_tool_calls: dict[str, dict] = {}

        for msg in result_messages:
            if msg.get("type") == "ai":
                usage_metadata = msg.get("usage_metadata") or {}
                usage = {
                    "prompt_tokens": usage_metadata.get("input_tokens", 0),
                    "completion_tokens": usage_metadata.get("output_tokens", 0),
                    "reasoning_tokens": usage_metadata.get("reasoning_tokens")
                        or usage_metadata.get("output_token_details", {}).get("reasoning_tokens", 0),
                }
                task.llm(model=MODEL_NAME, usage=usage, response=msg.get("content", ""))

                additional_kwargs = msg.get("additional_kwargs", {})
                reasoning = additional_kwargs.get("reasoning") or additional_kwargs.get("thinking") or ""
                if reasoning:
                    task.reasoning(reasoning)

                for tc in msg.get("tool_calls", []):
                    pending_tool_calls[tc.get("id", "")] = {"name": tc.get("name", ""), "input": tc.get("args", {})}

            elif msg.get("type") == "tool":
                tool_info = pending_tool_calls.pop(msg.get("tool_call_id", ""), {})
                task.tool(name=tool_info.get("name", "unknown"), input=tool_info.get("input", {}), output=msg.get("content", ""))

        for msg in reversed(result_messages):
            if msg.get("type") == "ai" and msg.get("content"):
                task.output(msg.get("content", ""))
                break

    return result
