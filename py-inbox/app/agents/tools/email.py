from __future__ import annotations

"""
Gmail tools for marlo-inbox agent.
"""

from email.utils import parseaddr
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from app.agents.tools import track_tool_call
from app.core.google_tools import get_gmail_service


class ListEmailsInput(BaseModel):
    max_results: int = 10


class GetEmailInput(BaseModel):
    email_id: str


class SearchEmailsInput(BaseModel):
    query: str
    max_results: int = 10


class DraftReplyInput(BaseModel):
    email_id: str
    instructions: str


class SendEmailInput(BaseModel):
    to: str
    subject: str
    body: str
    reply_to_id: str | None = None


async def _list_emails(max_results: int = 10) -> str:
    tool_input = {"max_results": max_results}
    try:
        service = get_gmail_service()
        emails = service.list_messages(max_results=max_results)
        result = _format_email_list(emails)
        track_tool_call(name="list_emails", tool_input=tool_input, tool_output=result)
        return result
    except Exception as exc:
        track_tool_call(
            name="list_emails",
            tool_input=tool_input,
            tool_output=None,
            error=str(exc),
        )
        raise


async def _get_email(email_id: str) -> str:
    tool_input = {"email_id": email_id}
    try:
        service = get_gmail_service()
        email_data = service.get_message(message_id=email_id, include_thread=True)
        result = _format_full_email(email_data)
        track_tool_call(name="get_email", tool_input=tool_input, tool_output=result)
        return result
    except Exception as exc:
        track_tool_call(
            name="get_email",
            tool_input=tool_input,
            tool_output=None,
            error=str(exc),
        )
        raise


async def _search_emails(query: str, max_results: int = 10) -> str:
    tool_input = {"query": query, "max_results": max_results}
    try:
        service = get_gmail_service()
        emails = service.search_messages(query=query, max_results=max_results)
        result = _format_email_list(emails)
        track_tool_call(name="search_emails", tool_input=tool_input, tool_output=result)
        return result
    except Exception as exc:
        track_tool_call(
            name="search_emails",
            tool_input=tool_input,
            tool_output=None,
            error=str(exc),
        )
        raise


async def _draft_reply(email_id: str, instructions: str) -> str:
    tool_input = {"email_id": email_id, "instructions": instructions}
    try:
        service = get_gmail_service()
        email_data = service.get_message(message_id=email_id, include_thread=False)
        message = email_data["message"]
        draft = _build_draft_reply(message, instructions)
        track_tool_call(name="draft_reply", tool_input=tool_input, tool_output=draft)
        return draft
    except Exception as exc:
        track_tool_call(
            name="draft_reply",
            tool_input=tool_input,
            tool_output=None,
            error=str(exc),
        )
        raise


async def _send_email(
    to: str,
    subject: str,
    body: str,
    reply_to_id: str | None = None,
) -> str:
    tool_input = {
        "to": to,
        "subject": subject,
        "body": body,
        "reply_to_id": reply_to_id,
    }
    try:
        service = get_gmail_service()
        thread_id = None
        in_reply_to = None
        references = None
        if reply_to_id:
            email_data = service.get_message(message_id=reply_to_id, include_thread=False)
            message = email_data["message"]
            thread_id = message.get("thread_id") or None
            in_reply_to = message.get("message_id") or None
            references = in_reply_to
            if not subject:
                subject = _reply_subject(message.get("subject", ""))

        response = service.send_message(
            to=to,
            subject=subject,
            body=body,
            thread_id=thread_id,
            in_reply_to=in_reply_to,
            references=references,
        )
        result = f"Email sent. ID: {response.get('id', '')}"
        track_tool_call(name="send_email", tool_input=tool_input, tool_output=result)
        return result
    except Exception as exc:
        track_tool_call(
            name="send_email",
            tool_input=tool_input,
            tool_output=None,
            error=str(exc),
        )
        raise


def _format_email_list(emails: list[dict[str, Any]]) -> str:
    if not emails:
        return "No emails found."

    lines = []
    for index, email in enumerate(emails, start=1):
        email_id = email.get("id", "")
        preview = (email.get("snippet") or "").replace("\n", " ").strip()
        lines.append(
            f"{index}. [ID: {email_id}] From: {email.get('from', '')} | "
            f"Subject: {email.get('subject', '')} | Date: {email.get('date', '')} | "
            f"Preview: {preview}"
        )
    return "\n".join(lines)


def _format_full_email(email_data: dict[str, Any]) -> str:
    message = email_data.get("message", {})
    thread = email_data.get("thread", [])

    lines = [
        "Email:",
        f"From: {message.get('from', '')}",
        f"To: {message.get('to', '')}",
        f"Date: {message.get('date', '')}",
        f"Subject: {message.get('subject', '')}",
        "",
        "--- Body ---",
        message.get("body", ""),
    ]

    if thread:
        lines.append("")
        lines.append("--- Thread ---")
        for index, item in enumerate(thread, start=1):
            lines.append(
                f"{index}. From: {item.get('from', '')} | Subject: {item.get('subject', '')} "
                f"| Date: {item.get('date', '')}"
            )
            body = item.get("body", "")
            if body:
                lines.append(body)
                lines.append("")

    return "\n".join(lines).strip()


def _build_draft_reply(message: dict[str, Any], instructions: str) -> str:
    sender_name, sender_email = parseaddr(message.get("from", ""))
    recipient = sender_email or message.get("from", "")
    greeting_name = sender_name or sender_email or "there"
    subject = _reply_subject(message.get("subject", ""))
    clean_instructions = instructions.strip()
    draft_body = f"Hi {greeting_name},\n\n{clean_instructions}\n\nBest,\n"

    lines = [
        "Draft reply:",
        f"To: {recipient}",
        f"Subject: {subject}",
        "",
        draft_body,
        "--- Original ---",
        f"From: {message.get('from', '')}",
        f"Subject: {message.get('subject', '')}",
        f"Date: {message.get('date', '')}",
        "",
        message.get("body", ""),
    ]
    return "\n".join(lines).strip()


def _reply_subject(subject: str) -> str:
    if subject.lower().startswith("re:"):
        return subject
    return f"Re: {subject}".strip()


list_emails = StructuredTool(
    name="list_emails",
    description="List recent emails from the user's Gmail inbox",
    args_schema=ListEmailsInput,
    coroutine=_list_emails,
)

get_email = StructuredTool(
    name="get_email",
    description="Get the full content of a specific email by ID, including the conversation thread",
    args_schema=GetEmailInput,
    coroutine=_get_email,
)

search_emails = StructuredTool(
    name="search_emails",
    description="Search emails by query (sender, subject, content). Uses Gmail search syntax.",
    args_schema=SearchEmailsInput,
    coroutine=_search_emails,
)

draft_reply = StructuredTool(
    name="draft_reply",
    description="Generate a reply draft for an email based on user instructions",
    args_schema=DraftReplyInput,
    coroutine=_draft_reply,
)

send_email = StructuredTool(
    name="send_email",
    description="Send an email or reply. If reply_to_id is provided, sends as a reply to that email thread.",
    args_schema=SendEmailInput,
    coroutine=_send_email,
)
