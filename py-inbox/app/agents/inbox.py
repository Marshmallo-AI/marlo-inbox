from __future__ import annotations

import logging
from functools import wraps
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

from app.core.config import settings
from app.core.google_tools import set_google_access_token
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

    def on_llm_start(self, serialized: dict, prompts: list, **kwargs: Any) -> None:
        logger.info(f"[marlo-callback] on_llm_start called - prompts count: {len(prompts)}")

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        logger.info("[marlo-callback] on_llm_end called")

        task_context = get_current_task()
        if not task_context:
            logger.warning("[marlo-callback] No task context available, skipping LLM tracking")
            return

        try:
            # Log response structure
            logger.info(f"[marlo-callback] response type: {type(response)}")
            logger.info(f"[marlo-callback] response.generations count: {len(response.generations) if response.generations else 0}")

            # Also check llm_output for token usage (some providers put it here)
            llm_output = getattr(response, "llm_output", None)
            logger.info(f"[marlo-callback] response.llm_output: {llm_output}")

            generation = response.generations[0][0] if response.generations else None
            if not generation:
                logger.warning("[marlo-callback] No generation found in response")
                return

            logger.info(f"[marlo-callback] generation type: {type(generation)}")
            logger.info(f"[marlo-callback] generation attributes: {dir(generation)}")

            response_content = generation.text or ""
            logger.info(f"[marlo-callback] response_content length: {len(response_content)}")

            # Extract token usage from message.usage_metadata (LangChain standard)
            input_tokens = 0
            output_tokens = 0
            reasoning_tokens = 0

            message = getattr(generation, "message", None)
            logger.info(f"[marlo-callback] message type: {type(message) if message else None}")

            if message:
                logger.info(f"[marlo-callback] message attributes: {dir(message)}")

                usage_metadata = getattr(message, "usage_metadata", None)
                logger.info(f"[marlo-callback] usage_metadata: {usage_metadata}")

                # Also check response_metadata
                response_metadata = getattr(message, "response_metadata", None)
                logger.info(f"[marlo-callback] response_metadata: {response_metadata}")

                if usage_metadata:
                    input_tokens = usage_metadata.get("input_tokens", 0)
                    output_tokens = usage_metadata.get("output_tokens", 0)
                    # Reasoning tokens in output_token_details for OpenAI
                    output_details = usage_metadata.get("output_token_details", {})
                    if output_details:
                        reasoning_tokens = output_details.get("reasoning", 0)
                    logger.info(f"[marlo-callback] Extracted from usage_metadata - input: {input_tokens}, output: {output_tokens}, reasoning: {reasoning_tokens}")

                # Fallback: check response_metadata.token_usage
                if input_tokens == 0 and output_tokens == 0 and response_metadata:
                    token_usage = response_metadata.get("token_usage", {})
                    if token_usage:
                        input_tokens = token_usage.get("prompt_tokens", 0)
                        output_tokens = token_usage.get("completion_tokens", 0)
                        reasoning_tokens = token_usage.get("reasoning_tokens", 0)
                        logger.info(f"[marlo-callback] Extracted from response_metadata.token_usage - input: {input_tokens}, output: {output_tokens}, reasoning: {reasoning_tokens}")

                # Extract reasoning if available (for extended thinking models)
                additional_kwargs = getattr(message, "additional_kwargs", {})
                reasoning = additional_kwargs.get("reasoning")
                if reasoning:
                    task_context.reasoning(reasoning)

            logger.info(f"[marlo-callback] Final token counts - input: {input_tokens}, output: {output_tokens}, reasoning: {reasoning_tokens}")

            # Track LLM call with token usage
            task_context.llm(
                model=MODEL_NAME,
                usage={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "reasoning_tokens": reasoning_tokens,
                },
                messages=[],
                response=response_content,
            )
            logger.info("[marlo-callback] Successfully tracked LLM call with Marlo")
        except Exception as e:
            logger.exception(f"[marlo-callback] Failed to track LLM call: {e}")


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

def _extract_and_set_credentials(config: RunnableConfig | None) -> None:
    """Extract credentials from config and set in context."""
    logger.info(f"[_extract_and_set_credentials] Called with config keys: {list(config.keys()) if config else 'None'}")

    if not config:
        logger.warning("[_extract_and_set_credentials] No config provided")
        return

    configurable = config.get("configurable", {})
    logger.info(f"[_extract_and_set_credentials] configurable keys: {list(configurable.keys()) if configurable else 'None'}")

    credentials = configurable.get("_credentials", {})
    logger.info(f"[_extract_and_set_credentials] credentials keys: {list(credentials.keys()) if credentials else 'None'}")

    access_token = credentials.get("access_token")

    if access_token:
        logger.info(f"[_extract_and_set_credentials] Setting Google access token (length: {len(access_token)})")
        set_google_access_token(access_token)
    else:
        logger.warning("[_extract_and_set_credentials] No access token found in credentials")
        set_google_access_token(None)


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


def _extract_messages(payload: Any) -> list:
    """Extract messages list from input payload."""
    if isinstance(payload, dict):
        messages = payload.get("messages")
        if isinstance(messages, list):
            return [
                {
                    "role": getattr(m, "type", "user") if hasattr(m, "type") else m.get("role", "user"),
                    "content": getattr(m, "content", "") if hasattr(m, "content") else m.get("content", ""),
                }
                for m in messages
            ]
    if isinstance(payload, list):
        return payload
    if isinstance(payload, str):
        return [{"role": "user", "content": payload}]
    return []


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

    marlo.init(api_key=MARLO_API_KEY)

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

        if msg_type == "AIMessage":
            tool_calls = getattr(message, "tool_calls", [])
            for tc in tool_calls:
                tool_id = tc.get("id")
                tool_name = tc.get("name")
                tool_args = tc.get("args", {})
                if tool_id and tool_name:
                    pending_tool_calls[tool_id] = {
                        "name": tool_name,
                        "input": tool_args,
                    }

        elif msg_type == "ToolMessage":
            tool_call_id = getattr(message, "tool_call_id", None)
            content = getattr(message, "content", "")
            if tool_call_id and tool_call_id in pending_tool_calls:
                tool_info = pending_tool_calls.pop(tool_call_id)
                try:
                    task.tool(
                        name=tool_info["name"],
                        input=tool_info["input"],
                        output=content,
                    )
                except Exception as e:
                    logger.warning(f"[marlo] Failed to track tool call: {e}")

    @wraps(_original_stream)
    def _marlo_stream(self, input_data, config=None, **kwargs):
        global _marlo_task_context
        _extract_and_set_credentials(config)
        thread_id = _get_thread_id(config)

        with marlo.task(
            thread_id=thread_id,
            agent=AGENT_NAME,
            thread_name="Inbox Pilot Chat",
        ) as task:
            _marlo_task_context = task
            user_input = _extract_task_text(input_data)
            task.input(user_input)

            final_answer = ""
            pending_tool_calls: dict[str, dict] = {}

            try:
                for chunk in _original_stream(self, input_data, config, **kwargs):
                    if isinstance(chunk, tuple) and len(chunk) >= 2:
                        event_type = chunk[0]
                        event_data = chunk[1]

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

                    yield chunk

                task.output(final_answer)

            except Exception as exc:
                task.error(str(exc))
                raise
            finally:
                _marlo_task_context = None

    @wraps(_original_astream)
    async def _marlo_astream(self, input_data, config=None, **kwargs):
        global _marlo_task_context
        _extract_and_set_credentials(config)
        thread_id = _get_thread_id(config)

        with marlo.task(
            thread_id=thread_id,
            agent=AGENT_NAME,
            thread_name="Inbox Pilot Chat",
        ) as task:
            _marlo_task_context = task
            user_input = _extract_task_text(input_data)
            task.input(user_input)

            final_answer = ""
            pending_tool_calls: dict[str, dict] = {}

            try:
                async for chunk in _original_astream(self, input_data, config, **kwargs):
                    if isinstance(chunk, tuple) and len(chunk) >= 2:
                        event_type = chunk[0]
                        event_data = chunk[1]

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

                    yield chunk

                task.output(final_answer)

            except Exception as exc:
                task.error(str(exc))
                raise
            finally:
                _marlo_task_context = None

    _base_agent.__class__.stream = _marlo_stream
    _base_agent.__class__.astream = _marlo_astream

agent = _base_agent
