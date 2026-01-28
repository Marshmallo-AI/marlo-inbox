from __future__ import annotations

"""
Inbox Pilot Agent - Email and Calendar Management.

This module creates a LangGraph ReAct agent for email and calendar management.
"""

import asyncio
import logging
import os
from functools import wraps
from typing import Any

import marlo
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.core.config import settings
from app.prompts import SYSTEM_PROMPT

# Initialize Marlo SDK for LangGraph server process
_MARLO_API_KEY = os.getenv("MARLO_API_KEY") or getattr(settings, "MARLO_API_KEY", None)
if _MARLO_API_KEY:
    marlo.init(api_key=_MARLO_API_KEY)
    logging.getLogger(__name__).info("[inbox] Marlo SDK initialized in LangGraph process")

from app.agents.tools.email import (
    draft_reply,
    get_email,
    list_emails,
    search_emails,
    send_email,
)
from app.agents.tools.calendar import (
    check_availability,
    create_event,
    delete_event,
    find_free_slots,
    get_schedule,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "inbox-pilot"
MODEL_NAME = "gpt-5"

llm = ChatOpenAI(
    model=MODEL_NAME,
    api_key=settings.OPENAI_API_KEY,
    temperature=1,
    stream_usage=True,
)

tools = [
    # Email tools
    list_emails,
    get_email,
    search_emails,
    draft_reply,
    send_email,
    # Calendar tools
    get_schedule,
    check_availability,
    find_free_slots,
    create_event,
    delete_event,
]

# Tool definitions for Marlo registration
TOOL_DEFINITIONS = [
    {"name": "list_emails", "description": "List recent emails from the user's Gmail inbox"},
    {"name": "get_email", "description": "Get the full content of a specific email by ID"},
    {"name": "search_emails", "description": "Search emails by query using Gmail search syntax"},
    {"name": "draft_reply", "description": "Generate a reply draft for an email"},
    {"name": "send_email", "description": "Send an email or reply to an existing thread"},
    {"name": "get_schedule", "description": "Get calendar events for a date or date range"},
    {"name": "check_availability", "description": "Check if a time slot is free or has conflicts"},
    {"name": "find_free_slots", "description": "Find available time slots for meetings"},
    {"name": "create_event", "description": "Create a new calendar event with optional attendees"},
    {"name": "delete_event", "description": "Delete or cancel a calendar event by ID"},
]


def register_agent() -> None:
    """Register agent definition with Marlo."""
    try:
        marlo.agent(
            name=AGENT_NAME,
            system_prompt=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            model_config={"model": MODEL_NAME, "temperature": 1},
        )
        logger.info("[inbox] Agent registered with Marlo")
    except Exception as e:
        logger.debug("[inbox] Marlo registration skipped: %s", e)


# Register agent with Marlo on module load
register_agent()

# Create the base agent
_base_agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=SYSTEM_PROMPT,
)

logger.info("[inbox] Base agent created")


# Marlo SDK Integration - Wrap agent stream methods
_marlo_task_context: Any = None


def _get_thread_id(config: dict | None) -> str:
    """Extract thread_id from config."""
    if config and isinstance(config, dict):
        configurable = config.get("configurable", {})
        if isinstance(configurable, dict):
            return str(configurable.get("thread_id", "default"))
    return "default"


def _extract_user_input(input_data: Any) -> str:
    """Extract user input text from input data."""
    if isinstance(input_data, dict):
        messages = input_data.get("messages", [])
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if hasattr(last, "content"):
                return str(getattr(last, "content", ""))
            if isinstance(last, dict):
                return str(last.get("content", ""))
    return ""


def _extract_messages(input_data: Any) -> list:
    """Extract messages list from input data."""
    if isinstance(input_data, dict):
        messages = input_data.get("messages", [])
        if isinstance(messages, list):
            return [
                {
                    "role": getattr(m, "type", "user") if hasattr(m, "type") else m.get("role", "user"),
                    "content": getattr(m, "content", "") if hasattr(m, "content") else m.get("content", ""),
                }
                for m in messages
            ]
    return []


def get_current_task() -> Any:
    """Get the current task context for tool tracking."""
    global _marlo_task_context
    return _marlo_task_context


def _inject_learnings(input_data: Any, learnings_text: str) -> Any:
    """Inject learnings as a system message into input data."""
    if not isinstance(input_data, dict):
        return input_data

    messages = input_data.get("messages", [])
    if not isinstance(messages, list):
        return input_data

    from langchain_core.messages import SystemMessage

    learnings_msg = SystemMessage(content=f"Learnings from past interactions:\n{learnings_text}")
    new_messages = [learnings_msg] + list(messages)

    return {**input_data, "messages": new_messages}


_original_stream = _base_agent.__class__.stream
_original_astream = _base_agent.__class__.astream


@wraps(_original_stream)
def _marlo_stream(self, input_data, config=None, **kwargs):
    """Wrapped stream method with Marlo tracking."""
    global _marlo_task_context
    thread_id = _get_thread_id(config)

    with marlo.task(thread_id=thread_id, agent=AGENT_NAME) as task:
        _marlo_task_context = task
        user_input = _extract_user_input(input_data)
        task.input(user_input)

        # Fetch and inject learnings
        learnings = task.get_learnings()
        if learnings:
            active = learnings.get("active", [])
            if active:
                learnings_text = "\n".join(
                    f"- {obj['learning']}" for obj in active if obj.get("learning")
                )
                if learnings_text:
                    input_data = _inject_learnings(input_data, learnings_text)
                    logger.info("[inbox] Injected %d learnings into agent context", len(active))

        final_answer = ""
        total_usage = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}
        try:
            for chunk in _original_stream(self, input_data, config, **kwargs):
                # Extract data from 2-tuple: (event_type, data)
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    event_type, event_data = chunk

                    # 'values' event contains final messages
                    if event_type == "values" and isinstance(event_data, dict):
                        messages = event_data.get("messages", [])
                        if messages:
                            last = messages[-1]
                            content = getattr(last, "content", None)
                            if content:
                                final_answer = str(content)

                    # 'messages' event contains streaming chunks with usage
                    elif event_type == "messages" and isinstance(event_data, tuple) and len(event_data) >= 1:
                        msg_chunk = event_data[0]
                        usage = getattr(msg_chunk, "usage_metadata", None)
                        if usage:
                            total_usage["input_tokens"] = usage.get("input_tokens", 0)
                            total_usage["output_tokens"] = usage.get("output_tokens", 0)
                            details = usage.get("output_token_details", {})
                            total_usage["reasoning_tokens"] = details.get("reasoning", 0)

                yield chunk

            task.llm(
                model=MODEL_NAME,
                usage={
                    "prompt_tokens": total_usage["input_tokens"],
                    "completion_tokens": total_usage["output_tokens"],
                    "reasoning_tokens": total_usage["reasoning_tokens"],
                },
                messages=_extract_messages(input_data),
                response=final_answer,
            )
            task.output(final_answer)

        except Exception as exc:
            task.error(str(exc))
            raise
        finally:
            _marlo_task_context = None


@wraps(_original_astream)
async def _marlo_astream(self, input_data, config=None, **kwargs):
    """Wrapped async stream method with Marlo tracking."""
    global _marlo_task_context
    thread_id = _get_thread_id(config)

    with marlo.task(thread_id=thread_id, agent=AGENT_NAME) as task:
        _marlo_task_context = task
        user_input = _extract_user_input(input_data)
        task.input(user_input)

        # Fetch and inject learnings (run in thread to avoid blocking event loop)
        try:
            learnings = await asyncio.to_thread(task.get_learnings)
            if learnings:
                active = learnings.get("active", [])
                if active:
                    learnings_text = "\n".join(
                        f"- {obj['learning']}" for obj in active if obj.get("learning")
                    )
                    if learnings_text:
                        input_data = _inject_learnings(input_data, learnings_text)
                        logger.info("[inbox] Injected %d learnings into agent context", len(active))
        except Exception as e:
            logger.warning("[inbox] Failed to fetch learnings: %s", e)

        final_answer = ""
        total_usage = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}
        try:
            async for chunk in _original_astream(self, input_data, config, **kwargs):
                # Extract data from 2-tuple: (event_type, data)
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    event_type, event_data = chunk

                    # 'values' event contains final messages
                    if event_type == "values" and isinstance(event_data, dict):
                        messages = event_data.get("messages", [])
                        if messages:
                            last = messages[-1]
                            content = getattr(last, "content", None)
                            if content:
                                final_answer = str(content)

                    # 'messages' event contains streaming chunks with usage
                    elif event_type == "messages" and isinstance(event_data, tuple) and len(event_data) >= 1:
                        msg_chunk = event_data[0]
                        usage = getattr(msg_chunk, "usage_metadata", None)
                        if usage:
                            total_usage["input_tokens"] = usage.get("input_tokens", 0)
                            total_usage["output_tokens"] = usage.get("output_tokens", 0)
                            details = usage.get("output_token_details", {})
                            total_usage["reasoning_tokens"] = details.get("reasoning", 0)

                yield chunk

            task.llm(
                model=MODEL_NAME,
                usage={
                    "prompt_tokens": total_usage["input_tokens"],
                    "completion_tokens": total_usage["output_tokens"],
                    "reasoning_tokens": total_usage["reasoning_tokens"],
                },
                messages=_extract_messages(input_data),
                response=final_answer,
            )
            task.output(final_answer)

        except Exception as exc:
            task.error(str(exc))
            raise
        finally:
            _marlo_task_context = None


# Apply Marlo wrappers to agent
_base_agent.__class__.stream = _marlo_stream
_base_agent.__class__.astream = _marlo_astream

logger.info("[inbox] Agent wrapped with Marlo tracking")

agent = _base_agent
