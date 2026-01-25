from __future__ import annotations

"""
Gmail tools for marlo-inbox agent.
"""

import asyncio
from email.utils import parseaddr
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.core.google_tools import get_access_token_from_config, GoogleAuthError
from app.services.gmail import GmailService


def _get_gmail_service(config: RunnableConfig) -> GmailService:
    """Get Gmail service - must be called within asyncio.to_thread."""
    access_token = get_access_token_from_config(config)
    if not access_token:
        raise GoogleAuthError("Not authenticated. Please log in first.")
    return GmailService(access_token)


def _list_emails_sync(config: RunnableConfig, max_results: int) -> list[dict[str, Any]]:
    """Synchronous wrapper for list_emails."""
    service = _get_gmail_service(config)
    return service.list_messages(max_results=max_results)


def _get_email_sync(config: RunnableConfig, email_id: str, include_thread: bool) -> dict[str, Any]:
    """Synchronous wrapper for get_email."""
    service = _get_gmail_service(config)
    return service.get_message(message_id=email_id, include_thread=include_thread)


def _search_emails_sync(config: RunnableConfig, query: str, max_results: int) -> list[dict[str, Any]]:
    """Synchronous wrapper for search_emails."""
    service = _get_gmail_service(config)
    return service.search_messages(query=query, max_results=max_results)


def _send_email_sync(
    config: RunnableConfig,
    to: str,
    subject: str,
    body: str,
    thread_id: str | None,
    in_reply_to: str | None,
    references: str | None,
) -> dict[str, Any]:
    """Synchronous wrapper for send_email."""
    service = _get_gmail_service(config)
    return service.send_message(
        to=to,
        subject=subject,
        body=body,
        thread_id=thread_id,
        in_reply_to=in_reply_to,
        references=references,
    )


@tool
async def list_emails(max_results: int = 10, *, config: RunnableConfig) -> str:
    """List recent emails from the user's Gmail inbox."""
    emails = await asyncio.to_thread(_list_emails_sync, config, max_results)
    return _format_email_list(emails)


@tool
async def get_email(email_id: str, *, config: RunnableConfig) -> str:
    """Get the full content of a specific email by ID, including the conversation thread."""
    email_data = await asyncio.to_thread(_get_email_sync, config, email_id, True)
    return _format_full_email(email_data)


@tool
async def search_emails(query: str, max_results: int = 10, *, config: RunnableConfig) -> str:
    """Search emails by query (sender, subject, content). Uses Gmail search syntax."""
    emails = await asyncio.to_thread(_search_emails_sync, config, query, max_results)
    return _format_email_list(emails)


@tool
async def draft_reply(email_id: str, instructions: str, *, config: RunnableConfig) -> str:
    """Generate a reply draft for an email based on user instructions."""
    email_data = await asyncio.to_thread(_get_email_sync, config, email_id, False)
    message = email_data["message"]
    return _build_draft_reply(message, instructions)


@tool
async def send_email(
    to: str,
    subject: str,
    body: str,
    reply_to_id: str | None = None,
    *,
    config: RunnableConfig,
) -> str:
    """Send an email or reply. If reply_to_id is provided, sends as a reply to that email thread."""
    thread_id = None
    in_reply_to = None
    references = None
    final_subject = subject

    if reply_to_id:
        email_data = await asyncio.to_thread(_get_email_sync, config, reply_to_id, False)
        message = email_data["message"]
        thread_id = message.get("thread_id") or None
        in_reply_to = message.get("message_id") or None
        references = in_reply_to
        if not final_subject:
            final_subject = _reply_subject(message.get("subject", ""))

    response = await asyncio.to_thread(
        _send_email_sync,
        config,
        to,
        final_subject,
        body,
        thread_id,
        in_reply_to,
        references,
    )
    return f"Email sent. ID: {response.get('id', '')}"


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
