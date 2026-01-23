from __future__ import annotations

import logging
from functools import wraps
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.agents.tools import set_marlo_task_context, track_tool_call
from app.core.config import settings
from app.prompts import SYSTEM_PROMPT

# Import tools - these will be implemented by Agent 2 and Agent 3
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

llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=settings.OPENAI_API_KEY,
    temperature=0.1,
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

agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=SYSTEM_PROMPT,
)

# --- Marlo Integration ---

MARLO_API_KEY = settings.MARLO_API_KEY

if MARLO_API_KEY:
    import marlo

    _tool_definitions = [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": (
                tool.args_schema.model_json_schema() if tool.args_schema else {}
            ),
        }
        for tool in tools
    ]

    marlo.agent(
        name="inbox-pilot",
        system_prompt=SYSTEM_PROMPT,
        tools=_tool_definitions,
        model_config={"model": "gpt-4o-mini", "temperature": 0.1},
    )

    _original_stream = agent.stream
    _original_astream = agent.astream

    @wraps(_original_stream)
    def _marlo_stream(input_data: dict[str, Any], config: dict | None = None, **kwargs):
        user_input = _extract_user_input(input_data)
        thread_id = config.get("configurable", {}).get("thread_id") if config else None

        with marlo.task(
            name="inbox-pilot",
            session_id=thread_id,
            metadata={"source": "langgraph"},
        ) as task:
            set_marlo_task_context(task)
            task.input(user_input)

            final_response = None
            for chunk in _original_stream(input_data, config, **kwargs):
                final_response = chunk
                yield chunk

            if final_response:
                output = _extract_output(final_response)
                task.output(output)

            set_marlo_task_context(None)

    @wraps(_original_astream)
    async def _marlo_astream(
        input_data: dict[str, Any], config: dict | None = None, **kwargs
    ):
        user_input = _extract_user_input(input_data)
        thread_id = config.get("configurable", {}).get("thread_id") if config else None

        with marlo.task(
            name="inbox-pilot",
            session_id=thread_id,
            metadata={"source": "langgraph"},
        ) as task:
            set_marlo_task_context(task)
            task.input(user_input)

            final_response = None
            async for chunk in _original_astream(input_data, config, **kwargs):
                final_response = chunk
                yield chunk

            if final_response:
                output = _extract_output(final_response)
                task.output(output)

            set_marlo_task_context(None)

    agent.stream = _marlo_stream
    agent.astream = _marlo_astream


def _extract_user_input(input_data: dict[str, Any]) -> str:
    """Extract user message from input data."""
    messages = input_data.get("messages", [])
    if not messages:
        return ""

    last_message = messages[-1]
    if isinstance(last_message, dict):
        return last_message.get("content", "")
    if hasattr(last_message, "content"):
        return last_message.content
    return str(last_message)


def _extract_output(response: dict[str, Any]) -> str:
    """Extract assistant response from agent output."""
    messages = response.get("messages", [])
    if not messages:
        return ""

    last_message = messages[-1]
    if isinstance(last_message, dict):
        return last_message.get("content", "")
    if hasattr(last_message, "content"):
        return last_message.content
    return str(last_message)
