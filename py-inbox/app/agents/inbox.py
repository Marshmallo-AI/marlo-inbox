from __future__ import annotations

"""
Inbox Pilot Agent with Marlo SDK integration.

This module creates a LangGraph ReAct agent for email and calendar management,
with Marlo tracking to capture all agent events (input, output, tool calls, LLM calls).

Marlo Integration Pattern:
--------------------------
Marlo is an observability SDK that captures agent execution events. It does NOT control
the agent - it only observes and records what happens. Events are collected during
execution and sent in batch when the task context exits.

The integration works by replacing stream/astream methods on the agent instance:
1. LangGraph loads the agent (must be a Graph type)
2. We replace stream/astream methods on the instance to add tracking
3. When called, the wrapper:
   - Opens marlo.task() context
   - Calls task.input() with user message
   - Streams from original method, collects messages
   - After stream completes, processes messages to extract tool calls and final answer
   - Reports via task.tool() and task.output()
   - Context exits -> Marlo flushes all events

LLM tracking is handled separately via LangChain callback (MarloLLMCallback).
"""

import logging
from collections.abc import AsyncGenerator, Generator
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

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
from app.core.config import settings
from app.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

AGENT_NAME = "inbox-pilot"
MODEL_NAME = "gpt-5"

# Global task context for LLM callback to access
# This is set when a Marlo task is active, None otherwise
_marlo_task_context: Any = None


def _get_current_task() -> Any:
    """Get the current Marlo task context for LLM callback tracking."""
    return _marlo_task_context


def _set_current_task(task: Any) -> None:
    """Set the current Marlo task context."""
    global _marlo_task_context
    _marlo_task_context = task


# =============================================================================
# LLM Callback for Marlo
# =============================================================================
# LangChain callbacks fire during LLM execution. We use this to capture
# LLM calls (model, token usage, messages, response) and report to Marlo.


class MarloLLMCallback(BaseCallbackHandler):
    """
    LangChain callback handler to capture LLM calls for Marlo tracking.

    This callback:
    1. on_llm_start: Captures input messages
    2. on_llm_end: Extracts token usage and response, reports to Marlo via task.llm()
    """

    def __init__(self) -> None:
        super().__init__()
        self._pending_messages: list[dict] = []

    def on_llm_start(self, serialized: dict, prompts: list, **kwargs: Any) -> None:
        """Capture input messages when LLM call starts."""
        self._pending_messages = []
        messages = kwargs.get("messages")
        if messages and isinstance(messages, list):
            for msg_list in messages:
                if isinstance(msg_list, list):
                    for msg in msg_list:
                        role = getattr(msg, "type", "user")
                        content = getattr(msg, "content", "")
                        self._pending_messages.append({"role": role, "content": str(content)})

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Extract response and token usage, report to Marlo."""
        task = _get_current_task()
        if not task:
            return

        try:
            generation = response.generations[0][0] if response.generations else None
            if not generation:
                return

            response_content = generation.text or ""

            # Extract token usage from various possible locations
            input_tokens = 0
            output_tokens = 0
            reasoning_tokens = 0

            message = getattr(generation, "message", None)
            if message:
                # Try usage_metadata first (newer LangChain format)
                usage_metadata = getattr(message, "usage_metadata", None)
                if usage_metadata:
                    input_tokens = usage_metadata.get("input_tokens", 0)
                    output_tokens = usage_metadata.get("output_tokens", 0)
                    output_details = usage_metadata.get("output_token_details", {})
                    if output_details:
                        reasoning_tokens = output_details.get("reasoning", 0)

                # Fallback to response_metadata (older format)
                if input_tokens == 0 and output_tokens == 0:
                    response_metadata = getattr(message, "response_metadata", {})
                    token_usage = response_metadata.get("token_usage", {})
                    if token_usage:
                        input_tokens = token_usage.get("prompt_tokens", 0)
                        output_tokens = token_usage.get("completion_tokens", 0)
                        reasoning_tokens = token_usage.get("reasoning_tokens", 0)

                # Track reasoning content if present (for reasoning models like o1, o3, gpt-5)
                # OpenAI reasoning models may store content in various locations
                reasoning_content = None

                # Check additional_kwargs (common location)
                additional_kwargs = getattr(message, "additional_kwargs", {})
                reasoning_content = additional_kwargs.get("reasoning") or additional_kwargs.get("reasoning_content")

                # Check direct message attribute
                if not reasoning_content:
                    reasoning_content = getattr(message, "reasoning_content", None)

                # Check response_metadata
                if not reasoning_content:
                    response_metadata = getattr(message, "response_metadata", {})
                    reasoning_content = response_metadata.get("reasoning") or response_metadata.get("reasoning_content")

                if reasoning_content:
                    task.reasoning(str(reasoning_content))
                    logger.debug(f"[marlo] Reasoning content captured: {len(str(reasoning_content))} chars")

            # Build messages list for tracking
            messages_to_track = self._pending_messages.copy()
            messages_to_track.append({"role": "assistant", "content": response_content})

            # Report LLM call to Marlo
            task.llm(
                model=MODEL_NAME,
                usage={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "reasoning_tokens": reasoning_tokens,
                },
                messages=messages_to_track,
                response=response_content,
            )
            logger.debug("[marlo] LLM call tracked")

        except Exception as e:
            logger.warning(f"[marlo] Failed to track LLM call: {e}")
        finally:
            self._pending_messages = []


# =============================================================================
# Agent Setup
# =============================================================================

marlo_callback = MarloLLMCallback()

llm = ChatOpenAI(
    model=MODEL_NAME,
    api_key=settings.OPENAI_API_KEY,
    temperature=1,
    stream_usage=True,
    callbacks=[marlo_callback],
    model_kwargs={
        "reasoning_effort": "high",  # Enable extended reasoning for complex email/calendar tasks
    },
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

# Create the base agent - this is a CompiledGraph that LangGraph expects
agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=SYSTEM_PROMPT,
)


# =============================================================================
# Marlo Tracking Helpers
# =============================================================================


def _get_thread_id(config: Any) -> str:
    """Extract thread_id from config for Marlo task grouping."""
    if config and isinstance(config, dict):
        configurable = config.get("configurable", {})
        if isinstance(configurable, dict):
            return configurable.get("thread_id", "default")
    return "default"


def _extract_user_input(payload: Any) -> str:
    """Extract user message from input payload."""
    if isinstance(payload, dict):
        messages = payload.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if hasattr(last, "content"):
                return str(last.content)
            if isinstance(last, dict):
                return str(last.get("content") or "")
    return ""


def _extract_messages_from_chunk(chunk: Any) -> list[Any]:
    """
    Extract complete messages from a stream chunk.

    LangGraph stream chunks can be:
    - Tuple with 3 elements: (namespace, event_type, data) - auth0 pattern
    - Tuple with 2 elements: (mode, data) - multiple stream modes
    - Dict: {"node_name": {"messages": [...]}} for updates mode

    We only collect complete messages (AIMessage, ToolMessage), not chunks.
    """
    messages = []

    # Debug: log chunk structure
    if isinstance(chunk, tuple):
        logger.debug(f"[marlo] Chunk tuple length: {len(chunk)}, types: {[type(c).__name__ for c in chunk]}")
        if len(chunk) >= 2:
            logger.debug(f"[marlo] Chunk[0]: {chunk[0]}, Chunk[1]: {type(chunk[1]).__name__}")
        if len(chunk) >= 3:
            logger.debug(f"[marlo] Chunk[2]: {type(chunk[2]).__name__}")

    # Handle tuple format with 3 elements: (namespace, event_type, data) - auth0 pattern
    if isinstance(chunk, tuple) and len(chunk) >= 3:
        event_type = chunk[1]
        event_data = chunk[2]

        if event_type == "values" and isinstance(event_data, dict):
            # values mode: {"messages": [...]}
            msgs = event_data.get("messages", [])
            messages.extend(msgs)
            logger.debug(f"[marlo] Extracted {len(msgs)} messages from 'values' event")

    # Handle tuple format with 2 elements: (mode, data)
    elif isinstance(chunk, tuple) and len(chunk) >= 2:
        mode, data = chunk[0], chunk[1]

        if mode == "updates" and isinstance(data, dict):
            # updates mode: {"node_name": {"messages": [...]}}
            for node_output in data.values():
                if isinstance(node_output, dict):
                    msgs = node_output.get("messages", [])
                    messages.extend(msgs)

        elif mode == "values" and isinstance(data, dict):
            # values mode: {"messages": [...]} - full state snapshot
            msgs = data.get("messages", [])
            messages.extend(msgs)
            logger.debug(f"[marlo] Extracted {len(msgs)} messages from 'values' mode (2-tuple)")

        elif mode in ("messages", "messages-tuple") and isinstance(data, tuple):
            # messages/messages-tuple mode: (message, metadata)
            msg = data[0]
            msg_type = type(msg).__name__
            if msg_type in ("AIMessage", "ToolMessage", "HumanMessage"):
                messages.append(msg)

    # Handle dict format directly: {"node_name": {"messages": [...]}}
    elif isinstance(chunk, dict):
        for node_output in chunk.values():
            if isinstance(node_output, dict):
                msgs = node_output.get("messages", [])
                messages.extend(msgs)

    else:
        # Unhandled chunk format - log at INFO level for debugging
        logger.info(f"[marlo] Unhandled chunk format: type={type(chunk).__name__}, value={str(chunk)[:200]}")

    if messages:
        logger.info(f"[marlo] Extracted {len(messages)} messages from chunk")

    return messages


def _process_collected_messages(messages: list[Any], task: Any) -> str:
    """
    Process collected messages after stream completes.

    This function:
    1. Finds AIMessage with tool_calls -> stores pending tool info
    2. Finds ToolMessage -> matches with pending tool call, reports to Marlo
    3. Finds final AIMessage (has content, no tool_calls) -> returns as final answer

    Args:
        messages: List of collected LangChain messages
        task: Marlo task context

    Returns:
        Final answer string (empty if none found)

    """
    # Pending tool calls: {tool_call_id: {"name": str, "input": dict}}
    pending_tools: dict[str, dict] = {}
    final_answer = ""

    for msg in messages:
        msg_type = type(msg).__name__

        if msg_type == "AIMessage":
            # Check for tool calls in this message
            tool_calls = getattr(msg, "tool_calls", [])

            if tool_calls:
                # Store pending tool calls for matching with ToolMessage
                for tc in tool_calls:
                    tool_id = tc.get("id")
                    tool_name = tc.get("name")
                    tool_args = tc.get("args", {})
                    if tool_id and tool_name:
                        pending_tools[tool_id] = {
                            "name": tool_name,
                            "input": tool_args,
                        }
                        logger.debug(f"[marlo] Pending tool call: {tool_name}")
            else:
                # AIMessage without tool_calls = potential final answer
                content = getattr(msg, "content", "")
                if content:
                    final_answer = str(content)

        elif msg_type == "ToolMessage":
            # Match with pending tool call and report to Marlo
            tool_call_id = getattr(msg, "tool_call_id", None)
            tool_output = getattr(msg, "content", "")
            tool_name = getattr(msg, "name", None)

            if tool_call_id and tool_call_id in pending_tools:
                tool_info = pending_tools.pop(tool_call_id)
                try:
                    task.tool(
                        name=tool_info["name"],
                        input=tool_info["input"],
                        output=tool_output,
                    )
                    logger.debug(f"[marlo] Tool tracked: {tool_info['name']}")
                except Exception as e:
                    logger.warning(f"[marlo] Failed to track tool {tool_info['name']}: {e}")

            elif tool_name:
                # Fallback: track with name only if tool_call_id not found
                try:
                    task.tool(
                        name=tool_name,
                        input={},
                        output=tool_output,
                    )
                    logger.debug(f"[marlo] Tool tracked (fallback): {tool_name}")
                except Exception as e:
                    logger.warning(f"[marlo] Failed to track tool {tool_name}: {e}")

    # Log warning if any tool calls weren't matched
    if pending_tools:
        logger.warning(f"[marlo] Unmatched tool calls: {list(pending_tools.keys())}")

    return final_answer


# =============================================================================
# Marlo Stream Wrappers
# =============================================================================
# We replace stream/astream methods on the agent INSTANCE (not the class)
# to add Marlo tracking while keeping the agent as a valid Graph type.

MARLO_API_KEY = settings.MARLO_API_KEY

if MARLO_API_KEY:
    import marlo

    # Initialize the SDK in the LangGraph server process.
    # Use init_in_thread() to avoid blocking async contexts.
    # This is safe to call at module load time.
    print(f"[marlo] Initializing SDK with API key: {MARLO_API_KEY[:20]}...{MARLO_API_KEY[-8:]}")
    marlo.init_in_thread(api_key=MARLO_API_KEY)
    print("[marlo] SDK initialization started in background thread")
    logger.info("[marlo] SDK initialization started in background thread")

    # Register agent definition with Marlo
    # This tells Marlo about the agent's configuration (tools, prompt, model)
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

    # Store original methods before replacing
    _original_stream = agent.stream
    _original_astream = agent.astream

    def _marlo_stream(
        self,
        input_data: Any,
        config: Any = None,
        **kwargs: Any,
    ) -> Generator[Any, None, None]:
        """
        Stream with Marlo tracking.

        Flow:
        1. Open marlo.task() context
        2. Record user input via task.input()
        3. Stream from original method, collect messages
        4. After stream ends, process messages for tool calls
        5. Record final answer via task.output()
        6. Context exits -> Marlo sends all events
        """
        thread_id = _get_thread_id(config)
        user_input = _extract_user_input(input_data)

        # Open Marlo task context - all events collected here
        with marlo.task(
            thread_id=thread_id,
            agent=AGENT_NAME,
        ) as task:
            # Set global context for LLM callback
            _set_current_task(task)

            # Record user input
            task.input(user_input)
            logger.info(f"[marlo] Task started for thread {thread_id}")

            # Collect messages during streaming
            collected_messages: list[Any] = []
            chunk_count = 0

            try:
                # Stream from original method (already bound, don't pass self)
                for chunk in _original_stream(input_data, config, **kwargs):
                    chunk_count += 1
                    # Collect complete messages from this chunk
                    messages = _extract_messages_from_chunk(chunk)
                    collected_messages.extend(messages)

                    # Yield chunk to caller (streaming continues normally)
                    yield chunk

                logger.info(
                    f"[marlo] Stream finished: {chunk_count} chunks, "
                    f"{len(collected_messages)} messages collected"
                )

                # Deduplicate messages by id if present
                seen_ids: set[str] = set()
                unique_messages: list[Any] = []
                for msg in collected_messages:
                    msg_id = getattr(msg, "id", None)
                    if msg_id:
                        if msg_id not in seen_ids:
                            seen_ids.add(msg_id)
                            unique_messages.append(msg)
                    else:
                        unique_messages.append(msg)

                if len(unique_messages) != len(collected_messages):
                    logger.info(
                        f"[marlo] Deduplicated: {len(collected_messages)} -> {len(unique_messages)} messages"
                    )

                # After stream completes, process collected messages
                final_answer = _process_collected_messages(unique_messages, task)

                # Record final output
                task.output(final_answer)
                logger.info(f"[marlo] Task completed, final_answer length: {len(final_answer)}")

            except Exception as exc:
                # Record error if something went wrong
                task.error(str(exc))
                logger.error(f"[marlo] Task error: {exc}")
                raise

            finally:
                # Clear global context
                _set_current_task(None)

    async def _marlo_astream(
        self,
        input_data: Any,
        config: Any = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Any, None]:
        """
        Async stream with Marlo tracking.

        Same flow as stream() but async.
        """
        thread_id = _get_thread_id(config)
        user_input = _extract_user_input(input_data)

        # Open Marlo task context
        print(f"[marlo] Opening task context for thread {thread_id}, agent {AGENT_NAME}")
        logger.info(f"[marlo] Opening task context for thread {thread_id}, agent {AGENT_NAME}")
        with marlo.task(
            thread_id=thread_id,
            agent=AGENT_NAME,
        ) as task:
            _set_current_task(task)
            task.input(user_input)
            print(f"[marlo] Async task started for thread {thread_id}")
            logger.info(f"[marlo] Async task started for thread {thread_id}")

            collected_messages: list[Any] = []
            chunk_count = 0

            try:
                # Stream from original method (already bound, don't pass self)
                async for chunk in _original_astream(input_data, config, **kwargs):
                    chunk_count += 1
                    messages = _extract_messages_from_chunk(chunk)
                    collected_messages.extend(messages)
                    yield chunk

                logger.info(
                    f"[marlo] Stream finished: {chunk_count} chunks, "
                    f"{len(collected_messages)} messages collected"
                )

                # Deduplicate messages by id if present
                seen_ids: set[str] = set()
                unique_messages: list[Any] = []
                for msg in collected_messages:
                    msg_id = getattr(msg, "id", None)
                    if msg_id:
                        if msg_id not in seen_ids:
                            seen_ids.add(msg_id)
                            unique_messages.append(msg)
                    else:
                        unique_messages.append(msg)

                if len(unique_messages) != len(collected_messages):
                    logger.info(
                        f"[marlo] Deduplicated: {len(collected_messages)} -> {len(unique_messages)} messages"
                    )

                final_answer = _process_collected_messages(unique_messages, task)
                task.output(final_answer)
                print(f"[marlo] Async task completed, final_answer length: {len(final_answer)}")
                logger.info(f"[marlo] Async task completed, final_answer length: {len(final_answer)}")

            except Exception as exc:
                task.error(str(exc))
                logger.error(f"[marlo] Async task error: {exc}")
                raise

            finally:
                _set_current_task(None)

    # Replace methods on the agent CLASS (not instance) to avoid LangGraph copy issue
    # Instance attributes get copied by LangGraph's copy() and cause __init__ errors
    # Class method replacement doesn't affect instance __dict__
    agent.__class__.stream = _marlo_stream
    agent.__class__.astream = _marlo_astream

    logger.info("[inbox] Marlo tracking enabled on agent class")

else:
    logger.warning("[inbox] MARLO_API_KEY not set - Marlo tracking disabled")
