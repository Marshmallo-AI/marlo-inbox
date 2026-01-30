from __future__ import annotations

"""
Gmail tools for marlo-inbox agent.
"""

import asyncio
import os
from email.utils import parseaddr
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.core.cache import (
    EMAIL_LIST_TTL,
    email_list_key,
    get_cache,
)
from app.core.google_tools import GoogleAuthError, get_access_token_from_config
from app.services.gmail import GmailService
from app.services.mock_gmail import MockGmailService


def _get_gmail_service(config: RunnableConfig) -> GmailService | MockGmailService:
    """Get Gmail service - must be called within asyncio.to_thread."""
    # Use mock service if MOCK_GMAIL env var is set
    if os.getenv("MOCK_GMAIL", "false").lower() == "true":
        return MockGmailService()

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
    from app.core.retry import format_user_error, with_retry

    cache = get_cache()
    user_id = "me"  # Gmail API uses "me" for authenticated user
    cache_key = email_list_key(user_id, max_results)

    # Try to get from cache
    cached_emails = cache.get(cache_key)
    if cached_emails is not None:
        print(f"[cache] Using cached email list ({len(cached_emails)} emails)")
        return _format_email_list(cached_emails)

    # Cache miss - fetch from API with retry logic
    try:
        emails = await with_retry(
            asyncio.to_thread,
            _list_emails_sync,
            config,
            max_results,
            max_retries=3,
        )

        # Store in cache
        cache.set(cache_key, emails, EMAIL_LIST_TTL)
        print(f"[cache] Cached email list ({len(emails)} emails, TTL: {EMAIL_LIST_TTL}s)")

        return _format_email_list(emails)

    except GoogleAuthError:
        # Don't fall back to cache for auth errors
        raise

    except Exception as e:
        # If API fails, try to use stale cache data
        print(f"[retry] API failed after retries: {e}")

        # Check if we have any cached data (even if expired)
        if cache_key in cache._cache:
            stale_emails, _ = cache._cache[cache_key]
            print(f"[cache] Using stale cached data ({len(stale_emails)} emails)")
            return (
                "⚠️ I'm having trouble accessing Gmail right now, but here's what I have cached:\n\n"
                + _format_email_list(stale_emails)
                + "\n\n(This data may be slightly outdated. Please try again in a moment.)"
            )

        # No cache available - return user-friendly error
        return format_user_error(e, "listing emails")


@tool
async def get_email(email_id: str, *, config: RunnableConfig) -> str:
    """Get the full content of a specific email by ID, including the conversation thread."""
    from app.core.cache import EMAIL_DETAIL_TTL, email_detail_key
    from app.core.retry import format_user_error, with_retry

    cache = get_cache()
    user_id = "me"
    cache_key = email_detail_key(user_id, email_id)

    # Try to get from cache
    cached_email = cache.get(cache_key)
    if cached_email is not None:
        print(f"[cache] Using cached email detail for {email_id}")
        return _format_full_email(cached_email)

    # Cache miss - fetch from API with retry logic
    try:
        email_data = await with_retry(
            asyncio.to_thread,
            _get_email_sync,
            config,
            email_id,
            True,
            max_retries=3,
        )

        # Store in cache
        cache.set(cache_key, email_data, EMAIL_DETAIL_TTL)
        print(f"[cache] Cached email detail for {email_id} (TTL: {EMAIL_DETAIL_TTL}s)")

        return _format_full_email(email_data)

    except GoogleAuthError:
        raise

    except Exception as e:
        # If API fails, try to use stale cache data
        print(f"[retry] API failed after retries: {e}")

        if cache_key in cache._cache:
            stale_email, _ = cache._cache[cache_key]
            print(f"[cache] Using stale cached data for {email_id}")
            return (
                "⚠️ I'm having trouble accessing Gmail right now, but here's the cached version:\n\n"
                + _format_full_email(stale_email)
                + "\n\n(This may be slightly outdated. Please try again in a moment.)"
            )

        return format_user_error(e, f"getting email {email_id}")


@tool
async def search_emails(query: str, max_results: int = 10, *, config: RunnableConfig) -> str:
    """Search emails by query (sender, subject, content). Uses Gmail search syntax."""
    from app.core.cache import EMAIL_SEARCH_TTL, email_search_key
    from app.core.retry import format_user_error, with_retry

    cache = get_cache()
    user_id = "me"
    cache_key = email_search_key(user_id, query, max_results)

    # Try to get from cache
    cached_emails = cache.get(cache_key)
    if cached_emails is not None:
        print(f"[cache] Using cached search results ({len(cached_emails)} emails)")
        return _format_email_list(cached_emails)

    # Cache miss - fetch from API with retry logic
    try:
        emails = await with_retry(
            asyncio.to_thread,
            _search_emails_sync,
            config,
            query,
            max_results,
            max_retries=3,
        )

        # Store in cache
        cache.set(cache_key, emails, EMAIL_SEARCH_TTL)
        print(f"[cache] Cached search results ({len(emails)} emails, TTL: {EMAIL_SEARCH_TTL}s)")

        return _format_email_list(emails)

    except GoogleAuthError:
        raise

    except Exception as e:
        # If API fails, try to use stale cache data
        print(f"[retry] API failed after retries: {e}")

        if cache_key in cache._cache:
            stale_emails, _ = cache._cache[cache_key]
            print(f"[cache] Using stale cached data ({len(stale_emails)} emails)")
            return (
                f"⚠️ I'm having trouble accessing Gmail right now, but here's what I have cached for '{query}':\n\n"
                + _format_email_list(stale_emails)
                + "\n\n(This data may be slightly outdated. Please try again in a moment.)"
            )

        return format_user_error(e, f"searching for emails matching '{query}'")


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
    from app.core.retry import format_user_error, with_retry

    thread_id = None
    in_reply_to = None
    references = None
    final_subject = subject

    try:
        if reply_to_id:
            email_data = await with_retry(
                asyncio.to_thread,
                _get_email_sync,
                config,
                reply_to_id,
                False,
                max_retries=2,
            )
            message = email_data["message"]
            thread_id = message.get("thread_id") or None
            in_reply_to = message.get("message_id") or None
            references = in_reply_to
            if not final_subject:
                final_subject = _reply_subject(message.get("subject", ""))

        response = await with_retry(
            asyncio.to_thread,
            _send_email_sync,
            config,
            to,
            final_subject,
            body,
            thread_id,
            in_reply_to,
            references,
            max_retries=3,
        )

        # Invalidate email list cache since we sent a new email
        cache = get_cache()
        cache.invalidate_pattern("emails:list:")
        cache.invalidate_pattern("emails:search:")

        return f"✅ Email sent successfully. ID: {response.get('id', '')}"

    except GoogleAuthError:
        raise

    except Exception as e:
        return format_user_error(e, "sending email")


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


def _batch_modify_emails_sync(
    config: RunnableConfig,
    email_ids: list[str],
    add_labels: list[str] | None,
    remove_labels: list[str] | None,
) -> dict[str, Any]:
    """Synchronous wrapper for batch_modify_emails."""
    service = _get_gmail_service(config)
    return service.batch_modify_messages(
        message_ids=email_ids,
        add_labels=add_labels,
        remove_labels=remove_labels,
    )


@tool
async def batch_process_emails(
    email_ids: list[str],
    action: str,
    *,
    config: RunnableConfig,
) -> str:
    """Process multiple emails in one operation for efficiency.

    This tool allows you to perform actions on multiple emails at once,
    which is much faster than processing them one by one.

    Args:
        email_ids: List of email IDs to process (from list_emails or search_emails)
        action: Action to perform. Supported actions:
            - "mark_read": Mark emails as read
            - "mark_unread": Mark emails as unread
            - "archive": Archive emails (remove from inbox)
            - "star": Star/flag emails as important
            - "unstar": Remove star from emails
            - "trash": Move emails to trash
            - "mark_important": Mark as important
            - "mark_not_important": Remove important flag
        config: Runtime configuration (automatically provided)

    Returns:
        Success message with count of processed emails

    Examples:
        - Mark all emails from a sender as read
        - Archive multiple notification emails at once
        - Star all emails about a specific project
        - Move multiple spam emails to trash

    """
    # Map actions to Gmail label operations
    action_map = {
        "mark_read": (None, ["UNREAD"]),
        "mark_unread": (["UNREAD"], None),
        "archive": (None, ["INBOX"]),
        "star": (["STARRED"], None),
        "unstar": (None, ["STARRED"]),
        "trash": (["TRASH"], ["INBOX"]),
        "mark_important": (["IMPORTANT"], None),
        "mark_not_important": (None, ["IMPORTANT"]),
    }

    if action not in action_map:
        return (
            f"Error: Unknown action '{action}'. "
            f"Supported actions: {', '.join(action_map.keys())}"
        )

    if not email_ids:
        return "Error: No email IDs provided"

    add_labels, remove_labels = action_map[action]

    try:
        from app.core.retry import format_user_error, with_retry

        await with_retry(
            asyncio.to_thread,
            _batch_modify_emails_sync,
            config,
            email_ids,
            add_labels,
            remove_labels,
            max_retries=3,
        )

        # Invalidate email list cache since we modified emails
        cache = get_cache()
        cache.invalidate_pattern("emails:list:")
        cache.invalidate_pattern("emails:search:")
        # Also invalidate individual email details that were modified
        for email_id in email_ids:
            cache.invalidate_pattern(f"emails:detail:me:{email_id}")

        count = len(email_ids)
        action_desc = action.replace("_", " ")
        return (
            f"✅ Successfully processed {count} email{'s' if count != 1 else ''}: {action_desc}\n"
            f"Email IDs: {', '.join(email_ids[:5])}"
            + (f" and {count - 5} more" if count > 5 else "")
        )
    except GoogleAuthError:
        raise
    except Exception as e:
        return format_user_error(e, f"batch processing {len(email_ids)} emails")
