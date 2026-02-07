"""Mock Calendar service for testing without OAuth."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


class MockCalendarService:
    """Mock Calendar service with realistic test data."""

    def __init__(self, access_token: str | None = None) -> None:
        """Initialize mock service (access_token ignored for testing)."""
        self._events = self._generate_mock_events()

    def _generate_mock_events(self) -> list[dict[str, Any]]:
        """Generate realistic mock calendar events."""
        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        return [
            {
                "id": "event001",
                "summary": "Team Standup",
                "start": {"dateTime": (today + timedelta(hours=9)).isoformat()},
                "end": {"dateTime": (today + timedelta(hours=9, minutes=30)).isoformat()},
                "attendees": [
                    {"email": "john@company.com"},
                    {"email": "jane@company.com"},
                ],
            },
            {
                "id": "event002",
                "summary": "Client Call - Acme Corp",
                "start": {"dateTime": (today + timedelta(hours=14)).isoformat()},
                "end": {"dateTime": (today + timedelta(hours=15)).isoformat()},
                "attendees": [{"email": "client@acme.com"}],
                "location": "Zoom",
            },
            {
                "id": "event003",
                "summary": "Focus Time - Code Review",
                "start": {"dateTime": (today + timedelta(hours=10)).isoformat()},
                "end": {"dateTime": (today + timedelta(hours=12)).isoformat()},
                "attendees": [],
            },
            {
                "id": "event004",
                "summary": "Team Lunch",
                "start": {"dateTime": (today + timedelta(days=2, hours=12, minutes=30)).isoformat()},
                "end": {"dateTime": (today + timedelta(days=2, hours=13, minutes=30)).isoformat()},
                "attendees": [
                    {"email": "team@company.com"},
                ],
                "location": "Italian Restaurant",
            },
            {
                "id": "event005",
                "summary": "Q4 Planning Meeting",
                "start": {"dateTime": (today + timedelta(days=5, hours=15)).isoformat()},
                "end": {"dateTime": (today + timedelta(days=5, hours=16, minutes=30)).isoformat()},
                "attendees": [
                    {"email": "john.doe@company.com"},
                    {"email": "sarah@company.com"},
                ],
            },
        ]

    def list_events(self, time_min: str, time_max: str) -> list[dict[str, Any]]:
        """List calendar events in a time range."""
        logger.info(f"[mock_calendar] Listing events from {time_min} to {time_max}")
        min_dt = datetime.fromisoformat(time_min.replace("Z", "+00:00"))
        max_dt = datetime.fromisoformat(time_max.replace("Z", "+00:00"))

        results = []
        for event in self._events:
            event_start = datetime.fromisoformat(
                event["start"]["dateTime"].replace("Z", "+00:00")
            )
            if min_dt <= event_start < max_dt:
                results.append(event)

        return sorted(results, key=lambda e: e["start"]["dateTime"])

    def get_freebusy(self, time_min: str, time_max: str) -> dict[str, Any]:
        """Get free/busy information."""
        logger.info(f"[mock_calendar] Getting freebusy from {time_min} to {time_max}")
        events = self.list_events(time_min, time_max)

        busy_times = [
            {"start": event["start"]["dateTime"], "end": event["end"]["dateTime"]}
            for event in events
        ]

        return {"calendars": {"primary": {"busy": busy_times}}}

    def create_event(
        self, event: dict[str, Any], send_updates: str = "none"
    ) -> dict[str, Any]:
        """Create a new calendar event (mock - just logs it)."""
        logger.info(f"[mock_calendar] Creating event: {event.get('summary')}")
        new_id = f"event{len(self._events) + 1:03d}"
        new_event = {**event, "id": new_id}
        self._events.append(new_event)
        return new_event

    def delete_event(self, event_id: str) -> None:
        """Delete a calendar event (mock - just logs it)."""
        logger.info(f"[mock_calendar] Deleting event: {event_id}")
        self._events = [e for e in self._events if e["id"] != event_id]

