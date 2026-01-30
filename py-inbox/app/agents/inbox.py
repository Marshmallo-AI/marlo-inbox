from __future__ import annotations

"""
Inbox Pilot Agent - Email and Calendar Management.

This module creates a LangGraph ReAct agent for email and calendar management.
Uses Marlo SDK's decorator and instrumentation pattern for automatic tracking.
"""

import asyncio
import logging
import os
from typing import Any

import marlo
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.core.config import settings
from app.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# === Marlo SDK Initialization ===
_MARLO_API_KEY = os.getenv("MARLO_API_KEY") or getattr(settings, "MARLO_API_KEY", None)
if _MARLO_API_KEY:
    marlo.init(api_key=_MARLO_API_KEY)
    # Instrument OpenAI globally - all LLM calls will be auto-tracked
    marlo.instrument_openai()
    logger.info("[inbox] Marlo SDK initialized with OpenAI instrumentation")

# === Agent Configuration ===
AGENT_NAME = "inbox-pilot"
MODEL_NAME = "gpt-5"

# === Tools (decorated with @marlo.track_tool) ===
from app.agents.tools.calendar import (
    check_availability,
    create_event,
    delete_event,
    find_free_slots,
    get_schedule,
)
from app.agents.tools.email import (
    batch_process_emails,
    draft_reply,
    get_email,
    list_emails,
    search_emails,
    send_email,
)

tools = [
    # Email tools
    list_emails,
    get_email,
    search_emails,
    draft_reply,
    send_email,
    batch_process_emails,  # NEW: Process multiple emails at once
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

# === LLM Setup ===
llm = ChatOpenAI(
    model=MODEL_NAME,
    api_key=settings.OPENAI_API_KEY,
    temperature=1,
    stream_usage=True,
    model_kwargs={
        "reasoning_effort": "high",  # Enable extended reasoning for complex email/calendar tasks
    },
)

# === Create Agent ===
agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=SYSTEM_PROMPT,
)

logger.info("[inbox] Agent created with Marlo tracking (decorators + instrumentation)")


# === Helper Functions ===
def get_thread_id(config: dict | None) -> str:
    """Extract thread_id from config."""
    if config and isinstance(config, dict):
        configurable = config.get("configurable", {})
        if isinstance(configurable, dict):
            return str(configurable.get("thread_id", "default"))
    return "default"


def extract_user_input(input_data: Any) -> str:
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


def inject_learnings(input_data: Any, learnings_text: str) -> Any:
    """Inject learnings as a system message into input data."""
    if not isinstance(input_data, dict):
        return input_data

    messages = input_data.get("messages", [])
    if not isinstance(messages, list):
        return input_data

    learnings_msg = SystemMessage(content=f"Learnings from past interactions:\n{learnings_text}")
    new_messages = [learnings_msg] + list(messages)

    return {**input_data, "messages": new_messages}


# === Marlo Task Wrapper ===
# This is a simple wrapper that creates a task boundary.
# Tool calls and LLM calls are auto-tracked via decorators and instrumentation.

async def run_with_marlo(
    input_data: Any,
    config: dict | None = None,
    **kwargs,
):
    """Run the agent with Marlo tracking.
    
    This is a simplified wrapper that:
    1. Creates a Marlo task boundary
    2. Injects learnings if available
    3. Captures final output
    
    Tool calls and LLM calls are automatically tracked via:
    - @marlo.track_tool decorator on tool functions
    - marlo.instrument_openai() called at module init
    """
    thread_id = get_thread_id(config)

    with marlo.task(thread_id=thread_id, agent=AGENT_NAME) as task:
        user_input = extract_user_input(input_data)
        task.input(user_input)

        # Fetch and inject learnings
        try:
            learnings = await asyncio.to_thread(task.get_learnings)
            if learnings:
                active = learnings.get("active", [])
                if active:
                    learnings_text = "\n".join(
                        f"- {obj['learning']}" for obj in active if obj.get("learning")
                    )
                    if learnings_text:
                        input_data = inject_learnings(input_data, learnings_text)
                        logger.info("[inbox] Injected %d learnings", len(active))
        except Exception as e:
            logger.warning("[inbox] Failed to fetch learnings: %s", e)

        final_answer = ""
        try:
            async for chunk in agent.astream(input_data, config, **kwargs):
                # Extract final answer from 'values' events
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    event_type, event_data = chunk
                    if event_type == "values" and isinstance(event_data, dict):
                        messages = event_data.get("messages", [])
                        if messages:
                            last = messages[-1]
                            content = getattr(last, "content", None)
                            if content and not hasattr(last, "tool_call_id"):
                                final_answer = str(content)
                yield chunk

            task.output(final_answer)

        except Exception as exc:
            task.error(str(exc))
            raise


# Export a simple stream function for backwards compatibility
async def stream(input_data: Any, config: dict | None = None, **kwargs):
    """Stream agent responses with Marlo tracking."""
    async for chunk in run_with_marlo(input_data, config, **kwargs):
        yield chunk
