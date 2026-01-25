from __future__ import annotations


def track_tool_call(*, name: str, tool_input, tool_output, error: str | None = None) -> None:
    """Track a tool call within the current Marlo task context."""
    try:
        from app.agents.inbox import get_current_task

        task = get_current_task()
        if task is not None:
            task.tool(
                name=name,
                input=tool_input,
                output=tool_output,
                error=error,
            )
    except Exception:
        pass
