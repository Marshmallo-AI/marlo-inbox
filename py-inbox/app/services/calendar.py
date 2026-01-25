from __future__ import annotations

import logging
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.google_tools import GoogleAuthError

logger = logging.getLogger(__name__)


def _handle_google_error(error: HttpError, operation: str) -> None:
    """Handle Google API HTTP errors and raise appropriate exceptions."""
    status = error.resp.status if error.resp else None
    logger.error(f"[calendar] {operation} failed with status {status}: {error}")
    if status in (401, 403):
        raise GoogleAuthError(
            f"Google authentication failed: {error.reason}. Please log in again."
        )
    raise


class CalendarService:
    def __init__(self, access_token: str) -> None:
        self._service = build(
            "calendar",
            "v3",
            credentials=Credentials(access_token),
        )

    def list_events(self, time_min: str, time_max: str) -> list[dict[str, Any]]:
        try:
            events = (
                self._service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
                .get("items", [])
            )
            return events
        except HttpError as e:
            _handle_google_error(e, "list_events")

    def get_freebusy(self, time_min: str, time_max: str) -> dict[str, Any]:
        try:
            return (
                self._service.freebusy()
                .query(
                    body={
                        "timeMin": time_min,
                        "timeMax": time_max,
                        "items": [{"id": "primary"}],
                    }
                )
                .execute()
            )
        except HttpError as e:
            _handle_google_error(e, "get_freebusy")

    def create_event(
        self,
        event: dict[str, Any],
        send_updates: str = "none",
    ) -> dict[str, Any]:
        try:
            return (
                self._service.events()
                .insert(
                    calendarId="primary",
                    body=event,
                    sendUpdates=send_updates,
                )
                .execute()
            )
        except HttpError as e:
            _handle_google_error(e, "create_event")

    def delete_event(self, event_id: str, send_updates: str = "all") -> None:
        try:
            self._service.events().delete(
                calendarId="primary",
                eventId=event_id,
                sendUpdates=send_updates,
            ).execute()
        except HttpError as e:
            _handle_google_error(e, "delete_event")
