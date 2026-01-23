from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_marlo_task_context: Any = None


def set_marlo_task_context(context: Any) -> None:
    """Set the current Marlo task context for tool tracking."""
    global _marlo_task_context
    _marlo_task_context = context


def get_marlo_task_context() -> Any:
    """Get the current Marlo task context."""
    return _marlo_task_context


def track_tool_call(
    name: str,
    tool_input: dict[str, Any],
    tool_output: Any,
    error: str | None = None,
) -> None:
    """
    Track a tool call with Marlo SDK.
    Called by each tool after execution to record the interaction.
    """
    context = get_marlo_task_context()
    if context is None:
        return

    try:
        context.tool(
            name=name,
            input=tool_input,
            output=tool_output if not error else None,
            error=error,
        )
    except Exception as e:
        logger.warning(f"Failed to track tool call: {e}")
