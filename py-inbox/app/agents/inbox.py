from __future__ import annotations

"""
Inbox Pilot Agent - Email and Calendar Management.

This module creates a LangGraph ReAct agent for email and calendar management.
"""

import logging

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.core.config import settings
from app.prompts import SYSTEM_PROMPT
import marlo

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

# Create the agent
agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=SYSTEM_PROMPT,
)

logger.info("[inbox] Agent created")
