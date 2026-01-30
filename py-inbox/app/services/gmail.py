from __future__ import annotations

import base64
import logging
from email.message import EmailMessage
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.google_tools import GoogleAuthError

logger = logging.getLogger(__name__)


def _handle_google_error(error: HttpError, operation: str) -> None:
    """Handle Google API HTTP errors and raise appropriate exceptions."""
    status = error.resp.status if error.resp else None
    logger.error(f"[gmail] {operation} failed with status {status}: {error}")
    if status in (401, 403):
        raise GoogleAuthError(
            f"Google authentication failed: {error.reason}. Please log in again."
        )
    raise


class GmailService:
    def __init__(self, access_token: str) -> None:
        self._service = build(
            "gmail",
            "v1",
            credentials=Credentials(access_token),
            cache_discovery=False,
        )

    def list_messages(self, max_results: int) -> list[dict[str, Any]]:
        try:
            messages = (
                self._service.users()
                .messages()
                .list(userId="me", labelIds=["INBOX"], maxResults=max_results)
                .execute()
                .get("messages", [])
            )
            return [self._get_message_metadata(message["id"]) for message in messages]
        except HttpError as e:
            _handle_google_error(e, "list_messages")

    def search_messages(self, query: str, max_results: int) -> list[dict[str, Any]]:
        try:
            messages = (
                self._service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=max_results,
                )
                .execute()
                .get("messages", [])
            )
            return [self._get_message_metadata(message["id"]) for message in messages]
        except HttpError as e:
            _handle_google_error(e, "search_messages")

    def get_message(self, message_id: str, include_thread: bool = True) -> dict[str, Any]:
        try:
            message = (
                self._service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            parsed_message = _parse_message(message)

            thread_messages = []
            if include_thread and message.get("threadId"):
                thread = (
                    self._service.users()
                    .threads()
                    .get(userId="me", id=message["threadId"], format="full")
                    .execute()
                )
                thread_messages = [_parse_message(item) for item in thread.get("messages", [])]

            return {
                "message": parsed_message,
                "thread": thread_messages,
            }
        except HttpError as e:
            _handle_google_error(e, "get_message")

    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> dict[str, Any]:
        try:
            message = EmailMessage()
            message["To"] = to
            message["Subject"] = subject
            if in_reply_to:
                message["In-Reply-To"] = in_reply_to
            if references:
                message["References"] = references
            message.set_content(body)

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            send_body: dict[str, Any] = {"raw": raw_message}
            if thread_id:
                send_body["threadId"] = thread_id

            return (
                self._service.users()
                .messages()
                .send(userId="me", body=send_body)
                .execute()
            )
        except HttpError as e:
            _handle_google_error(e, "send_message")

    def batch_modify_messages(
        self,
        message_ids: list[str],
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Modify multiple messages in a single API call.

        Args:
            message_ids: List of message IDs to modify
            add_labels: Labels to add (e.g., ["STARRED", "IMPORTANT"])
            remove_labels: Labels to remove (e.g., ["UNREAD", "INBOX"])

        Common label IDs:
            - INBOX, UNREAD, STARRED, IMPORTANT, TRASH, SPAM
            - User labels can be retrieved via users().labels().list()

        """
        try:
            body: dict[str, Any] = {"ids": message_ids}
            if add_labels:
                body["addLabelIds"] = add_labels
            if remove_labels:
                body["removeLabelIds"] = remove_labels

            return (
                self._service.users()
                .messages()
                .batchModify(userId="me", body=body)
                .execute()
            )
        except HttpError as e:
            _handle_google_error(e, "batch_modify_messages")

    def _get_message_metadata(self, message_id: str) -> dict[str, Any]:
        try:
            message = (
                self._service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="metadata",
                    metadataHeaders=["From", "To", "Subject", "Date"],
                )
                .execute()
            )
            headers = {
                header["name"]: header.get("value", "")
                for header in message.get("payload", {}).get("headers", [])
            }
            return {
                "id": message["id"],
                "thread_id": message.get("threadId", ""),
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": message.get("snippet", ""),
            }
        except HttpError as e:
            _handle_google_error(e, "_get_message_metadata")


def _parse_message(message: dict[str, Any]) -> dict[str, Any]:
    payload = message.get("payload", {})
    headers = {header["name"]: header.get("value", "") for header in payload.get("headers", [])}
    body = _extract_body(payload)
    return {
        "id": message.get("id", ""),
        "thread_id": message.get("threadId", ""),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "subject": headers.get("Subject", ""),
        "date": headers.get("Date", ""),
        "message_id": headers.get("Message-ID", ""),
        "snippet": message.get("snippet", ""),
        "body": body,
    }


def _extract_body(payload: dict[str, Any]) -> str:
    parts: list[tuple[str, str]] = []
    _collect_parts(payload, parts)

    for mime_type in ("text/plain", "text/html"):
        for part_mime, part_data in parts:
            if part_mime == mime_type:
                return _decode_body(part_data)
    return ""


def _collect_parts(payload: dict[str, Any], parts: list[tuple[str, str]]) -> None:
    if payload.get("parts"):
        for part in payload["parts"]:
            _collect_parts(part, parts)
        return

    body = payload.get("body", {})
    data = body.get("data")
    mime_type = payload.get("mimeType", "")
    if data:
        parts.append((mime_type, data))


def _decode_body(data: str) -> str:
    try:
        decoded = base64.urlsafe_b64decode(data.encode("utf-8"))
        return decoded.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("Failed to decode Gmail body: %s", exc)
        return ""
