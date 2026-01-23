from __future__ import annotations

import logging
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


class CalendarService:
    def __init__(self, access_token: str) -> None:
        self._service = build(
            "calendar",
            "v3",
            credentials=Credentials(access_token),
        )

    def list_events(self, time_min: str, time_max: str) -> list[dict[str, Any]]:
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

    def get_freebusy(self, time_min: str, time_max: str) -> dict[str, Any]:
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

    def create_event(
        self,
        event: dict[str, Any],
        send_updates: str = "none",
    ) -> dict[str, Any]:
        return (
            self._service.events()
            .insert(
                calendarId="primary",
                body=event,
                sendUpdates=send_updates,
            )
            .execute()
        )

    def delete_event(self, event_id: str, send_updates: str = "all") -> None:
        self._service.events().delete(
            calendarId="primary",
            eventId=event_id,
            sendUpdates=send_updates,
        ).execute()
