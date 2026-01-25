from __future__ import annotations

import logging
from functools import wraps
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langgraph.prebuilt import create_react_agent

from app.core.config import settings
from app.prompts import SYSTEM_PROMPT

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

_marlo_task_context: Any = None


def get_current_task() -> Any:
    """Get the current Marlo task context for tool tracking."""
    global _marlo_task_context
    return _marlo_task_context


class MarloLLMCallback(BaseCallbackHandler):
    """Callback handler to capture LLM calls for Marlo."""

    def __init__(self) -> None:
        super().__init__()
        self._pending_messages: list[dict] = []

    def on_llm_start(self, serialized: dict, prompts: list, **kwargs: Any) -> None:
        logger.debug(f"[marlo-callback] on_llm_start called - prompts count: {len(prompts)}")
        self._pending_messages = []
        messages = kwargs.get("messages")
        if messages and isinstance(messages, list) and messages:
            for msg_list in messages:
                if isinstance(msg_list, list):
                    for msg in msg_list:
                        role = getattr(msg, "type", "user")
                        content = getattr(msg, "content", "")
                        self._pending_messages.append({"role": role, "content": str(content)})

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        logger.debug("[marlo-callback] on_llm_end called")

        task_context = get_current_task()
        if not task_context:
            logger.debug("[marlo-callback] No task context available, skipping LLM tracking")
            return

        try:
            generation = response.generations[0][0] if response.generations else None
            if not generation:
                logger.warning("[marlo-callback] No generation found in response")
                return

            response_content = generation.text or ""

            input_tokens = 0
            output_tokens = 0
            reasoning_tokens = 0

            message = getattr(generation, "message", None)

            if message:
                usage_metadata = getattr(message, "usage_metadata", None)
                response_metadata = getattr(message, "response_metadata", None)

                if usage_metadata:
                    input_tokens = usage_metadata.get("input_tokens", 0)
                    output_tokens = usage_metadata.get("output_tokens", 0)
                    output_details = usage_metadata.get("output_token_details", {})
                    if output_details:
                        reasoning_tokens = output_details.get("reasoning", 0)

                if input_tokens == 0 and output_tokens == 0 and response_metadata:
                    token_usage = response_metadata.get("token_usage", {})
                    if token_usage:
                        input_tokens = token_usage.get("prompt_tokens", 0)
                        output_tokens = token_usage.get("completion_tokens", 0)
                        reasoning_tokens = token_usage.get("reasoning_tokens", 0)

                additional_kwargs = getattr(message, "additional_kwargs", {})
                reasoning = additional_kwargs.get("reasoning")
                if reasoning:
                    task_context.reasoning(reasoning)

            messages_to_track = self._pending_messages.copy()
            messages_to_track.append({"role": "assistant", "content": response_content})

            task_context.llm(
                model=MODEL_NAME,
                usage={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "reasoning_tokens": reasoning_tokens,
                },
                messages=messages_to_track,
                response=response_content,
            )
            logger.debug("[marlo-callback] Successfully tracked LLM call with Marlo")
        except Exception as e:
            logger.exception(f"[marlo-callback] Failed to track LLM call: {e}")
        finally:
            self._pending_messages = []


marlo_callback = MarloLLMCallback()

llm = ChatOpenAI(
    model=MODEL_NAME,
    api_key=settings.OPENAI_API_KEY,
    temperature=1,
    stream_usage=True,
    callbacks=[marlo_callback],
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

_base_agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=SYSTEM_PROMPT,
)

# --- Marlo SDK Integration ---

MARLO_API_KEY = settings.MARLO_API_KEY


def _extract_task_text(payload: Any) -> str:
    """Extract user message from input payload."""
    if isinstance(payload, dict):
        messages = payload.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if hasattr(last, "content"):
                return str(getattr(last, "content"))
            if isinstance(last, dict):
                return str(last.get("content") or "Task")
    return "Task"


def _extract_final_answer(result: Any) -> str:
    """Extract final answer from agent result."""
    if isinstance(result, dict):
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if hasattr(last, "content"):
                return str(getattr(last, "content") or "")
            if isinstance(last, dict):
                return str(last.get("content") or "")
    return ""


if MARLO_API_KEY:
    import marlo

    _tool_definitions = []
    for t in tools:
        tool_def = {
            "name": t.name,
            "description": t.description,
        }
        if hasattr(t, "args_schema") and t.args_schema:
            try:
                tool_def["parameters"] = t.args_schema.model_json_schema()
            except Exception:
                pass
        _tool_definitions.append(tool_def)

    marlo.agent(
        name=AGENT_NAME,
        system_prompt=SYSTEM_PROMPT,
        tools=_tool_definitions,
        mcp=[],
        model_config={"model": MODEL_NAME, "temperature": 1},
    )

    def _get_thread_id(config: Any) -> str:
        if config and isinstance(config, dict):
            configurable = config.get("configurable", {})
            if isinstance(configurable, dict):
                return configurable.get("thread_id", "default")
        return "default"

    _original_stream = _base_agent.__class__.stream
    _original_astream = _base_agent.__class__.astream

    def _process_message_for_tools(message: Any, task: Any, pending_tool_calls: dict) -> None:
        """Process a message to extract and track tool calls."""
        msg_type = type(message).__name__
        logger.debug(f"[marlo] Processing message type: {msg_type}")

        if msg_type == "AIMessage":
            tool_calls = getattr(message, "tool_calls", [])
            logger.debug(f"[marlo] AIMessage has {len(tool_calls)} tool calls")
            for tc in tool_calls:
                tool_id = tc.get("id")
                tool_name = tc.get("name")
                tool_args = tc.get("args", {})
                if tool_id and tool_name:
                    logger.info(f"[marlo] Pending tool call: {tool_name} (id={tool_id})")
                    pending_tool_calls[tool_id] = {
                        "name": tool_name,
                        "input": tool_args,
                    }

        elif msg_type == "ToolMessage":
            tool_call_id = getattr(message, "tool_call_id", None)
            content = getattr(message, "content", "")
            tool_name = getattr(message, "name", None)
            logger.info(f"[marlo] ToolMessage received: tool_call_id={tool_call_id}, name={tool_name}")

            if tool_call_id and tool_call_id in pending_tool_calls:
                tool_info = pending_tool_calls.pop(tool_call_id)
                logger.info(f"[marlo] Tracking tool call: {tool_info['name']}")
                try:
                    task.tool(
                        name=tool_info["name"],
                        input=tool_info["input"],
                        output=content,
                    )
                    logger.info(f"[marlo] Successfully tracked tool: {tool_info['name']}")
                except Exception as e:
                    logger.warning(f"[marlo] Failed to track tool call: {e}")
            elif tool_call_id:
                # Tool call ID not in pending - try to track with available info
                logger.warning(f"[marlo] Tool call ID {tool_call_id} not in pending calls, tracking with name={tool_name}")
                if tool_name:
                    try:
                        task.tool(
                            name=tool_name,
                            input={},
                            output=content,
                        )
                        logger.info(f"[marlo] Tracked tool (fallback): {tool_name}")
                    except Exception as e:
                        logger.warning(f"[marlo] Failed to track tool call (fallback): {e}")

    def _process_chunk_for_tools(chunk: Any, task: Any, pending_tool_calls: dict) -> str | None:
        """Process any chunk format to extract tool calls and final answer."""
        final_answer = None

        # Handle tuple format: ("event_type", data)
        if isinstance(chunk, tuple) and len(chunk) >= 2:
            event_type, event_data = chunk[0], chunk[1]
            logger.debug(f"[marlo] Tuple chunk: event_type={event_type}")

            if event_type == "messages":
                message = event_data[0] if isinstance(event_data, tuple) else event_data
                _process_message_for_tools(message, task, pending_tool_calls)
                msg_type = type(message).__name__
                if msg_type == "AIMessage":
                    content = getattr(message, "content", "")
                    if content and not getattr(message, "tool_calls", []):
                        final_answer = str(content)

            elif event_type == "updates":
                if isinstance(event_data, dict):
                    for node_name, node_output in event_data.items():
                        messages = node_output.get("messages", []) if isinstance(node_output, dict) else []
                        for msg in messages:
                            _process_message_for_tools(msg, task, pending_tool_calls)
                            msg_type = type(msg).__name__
                            if msg_type == "AIMessage":
                                content = getattr(msg, "content", "")
                                if content and not getattr(msg, "tool_calls", []):
                                    final_answer = str(content)

        # Handle dict format: {"node_name": {"messages": [...]}}
        elif isinstance(chunk, dict):
            logger.debug(f"[marlo] Dict chunk with keys: {list(chunk.keys())}")
            for node_name, node_output in chunk.items():
                if isinstance(node_output, dict):
                    messages = node_output.get("messages", [])
                    for msg in messages:
                        _process_message_for_tools(msg, task, pending_tool_calls)
                        msg_type = type(msg).__name__
                        if msg_type == "AIMessage":
                            content = getattr(msg, "content", "")
                            if content and not getattr(msg, "tool_calls", []):
                                final_answer = str(content)

        return final_answer

    @wraps(_original_stream)
    def _marlo_stream(self, input_data, config=None, **kwargs):
        global _marlo_task_context
        logger.info("[marlo_stream] WRAPPER CALLED")
        thread_id = _get_thread_id(config)

        with marlo.task(
            thread_id=thread_id,
            agent=AGENT_NAME,
            thread_name="Inbox Pilot Chat",
        ) as task:
            _marlo_task_context = task
            user_input = _extract_task_text(input_data)
            task.input(user_input)
            logger.info(f"[marlo] Started task for thread {thread_id}")

            final_answer = ""
            pending_tool_calls: dict[str, dict] = {}

            try:
                for chunk in _original_stream(self, input_data, config, **kwargs):
                    # Process chunk for tool calls
                    answer = _process_chunk_for_tools(chunk, task, pending_tool_calls)
                    if answer:
                        final_answer = answer

                    yield chunk

                # Log any pending tool calls that weren't completed
                if pending_tool_calls:
                    logger.warning(f"[marlo] {len(pending_tool_calls)} pending tool calls not completed: {list(pending_tool_calls.keys())}")

                task.output(final_answer)
                logger.info(f"[marlo] Task completed with final_answer length: {len(final_answer)}")

            except Exception as exc:
                task.error(str(exc))
                raise
            finally:
                _marlo_task_context = None

    @wraps(_original_astream)
    async def _marlo_astream(self, input_data, config=None, **kwargs):
        global _marlo_task_context
        logger.info("[marlo_astream] WRAPPER CALLED")
        thread_id = _get_thread_id(config)

        with marlo.task(
            thread_id=thread_id,
            agent=AGENT_NAME,
            thread_name="Inbox Pilot Chat",
        ) as task:
            _marlo_task_context = task
            user_input = _extract_task_text(input_data)
            task.input(user_input)
            logger.info(f"[marlo] Started async task for thread {thread_id}")

            final_answer = ""
            pending_tool_calls: dict[str, dict] = {}

            try:
                async for chunk in _original_astream(self, input_data, config, **kwargs):
                    # Process chunk for tool calls
                    answer = _process_chunk_for_tools(chunk, task, pending_tool_calls)
                    if answer:
                        final_answer = answer

                    yield chunk

                # Log any pending tool calls that weren't completed
                if pending_tool_calls:
                    logger.warning(f"[marlo] {len(pending_tool_calls)} pending tool calls not completed: {list(pending_tool_calls.keys())}")

                task.output(final_answer)
                logger.info(f"[marlo] Async task completed with final_answer length: {len(final_answer)}")

            except Exception as exc:
                task.error(str(exc))
                raise
            finally:
                _marlo_task_context = None

    _base_agent.__class__.stream = _marlo_stream
    _base_agent.__class__.astream = _marlo_astream
    logger.info("[inbox] Marlo wrappers applied to agent stream/astream methods")

else:
    logger.warning("[inbox] MARLO_API_KEY not set - Marlo tracking disabled")

agent = _base_agent
logger.info(f"[inbox] Agent module loaded. MARLO_API_KEY set: {bool(MARLO_API_KEY)}")
