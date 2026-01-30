"""Mock Gmail service for testing without OAuth."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class MockGmailService:
    """Mock Gmail service with realistic test data."""

    def __init__(self, access_token: str | None = None) -> None:
        """Initialize mock service (access_token ignored for testing)."""
        self._emails = self._generate_mock_emails()

    def _generate_mock_emails(self) -> list[dict[str, Any]]:
        """Generate realistic mock email data."""
        now = datetime.now(UTC)
        return [
            {
                "id": "msg001",
                "thread_id": "thread001",
                "from": "john.doe@company.com",
                "to": "you@example.com",
                "subject": "Q4 Planning Meeting - Action Required",
                "date": now.isoformat(),
                "snippet": "Hi, we need to schedule our Q4 planning meeting. Can you share your availability for next week?",
                "body": "Hi,\n\nWe need to schedule our Q4 planning meeting. Can you share your availability for next week?\n\nPreferably Tuesday or Wednesday afternoon.\n\nBest,\nJohn",
                "message_id": "<msg001@company.com>",
                "labels": ["INBOX", "IMPORTANT"],
            },
            {
                "id": "msg002",
                "thread_id": "thread002",
                "from": "jane.smith@client.com",
                "to": "you@example.com",
                "subject": "Project Update - Review Needed",
                "date": (now.replace(hour=now.hour - 2)).isoformat(),
                "snippet": "Please review the attached project timeline and provide feedback by EOD.",
                "body": "Hi,\n\nPlease review the attached project timeline and provide feedback by EOD.\n\nLet me know if you have any questions.\n\nThanks,\nJane",
                "message_id": "<msg002@client.com>",
                "labels": ["INBOX"],
            },
            {
                "id": "msg003",
                "thread_id": "thread003",
                "from": "notifications@github.com",
                "to": "you@example.com",
                "subject": "[marlo-inbox] New PR #42: Add email batching",
                "date": (now.replace(hour=now.hour - 5)).isoformat(),
                "snippet": "A new pull request has been opened by @contributor",
                "body": "A new pull request has been opened:\n\nTitle: Add email batching\nAuthor: @contributor\n\nView PR: https://github.com/...",
                "message_id": "<msg003@github.com>",
                "labels": ["INBOX", "CATEGORY_UPDATES"],
            },
            {
                "id": "msg004",
                "thread_id": "thread004",
                "from": "sarah.johnson@partner.com",
                "to": "you@example.com",
                "subject": "Re: Partnership Discussion",
                "date": (now.replace(day=now.day - 1)).isoformat(),
                "snippet": "Thanks for the call yesterday. Here are the next steps we discussed...",
                "body": "Hi,\n\nThanks for the call yesterday. Here are the next steps we discussed:\n\n1. Review the proposal\n2. Schedule follow-up meeting\n3. Prepare contract draft\n\nLooking forward to working together!\n\nBest,\nSarah",
                "message_id": "<msg004@partner.com>",
                "labels": ["INBOX"],
            },
            {
                "id": "msg005",
                "thread_id": "thread005",
                "from": "team@company.com",
                "to": "you@example.com",
                "subject": "Team Lunch - Friday 12:30 PM",
                "date": (now.replace(day=now.day - 2)).isoformat(),
                "snippet": "Reminder: Team lunch this Friday at 12:30 PM at the Italian place.",
                "body": "Hi team,\n\nReminder: Team lunch this Friday at 12:30 PM at the Italian place.\n\nPlease RSVP by Thursday.\n\nCheers!",
                "message_id": "<msg005@company.com>",
                "labels": ["INBOX"],
            },
        ]

    def list_messages(self, max_results: int = 10) -> list[dict[str, Any]]:
        """List recent emails."""
        logger.info(f"[mock_gmail] Listing {max_results} messages")
        return self._emails[:max_results]

    def get_message(
        self, message_id: str, include_thread: bool = False
    ) -> dict[str, Any]:
        """Get a specific email by ID."""
        logger.info(f"[mock_gmail] Getting message {message_id}")
        email = next((e for e in self._emails if e["id"] == message_id), None)
        if not email:
            raise ValueError(f"Email {message_id} not found")

        result = {"message": email}
        if include_thread:
            # Return emails in the same thread
            thread_emails = [
                e for e in self._emails if e["thread_id"] == email["thread_id"]
            ]
            result["thread"] = thread_emails

        return result

    def search_messages(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """Search emails by query."""
        logger.info(f"[mock_gmail] Searching for: {query}")
        query_lower = query.lower()
        results = [
            e
            for e in self._emails
            if query_lower in e["subject"].lower()
            or query_lower in e["from"].lower()
            or query_lower in e["body"].lower()
        ]
        return results[:max_results]

    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> dict[str, Any]:
        """Send an email (mock - just logs it)."""
        logger.info(f"[mock_gmail] Sending email to {to}: {subject}")
        new_id = f"msg{len(self._emails) + 1:03d}"
        return {
            "id": new_id,
            "threadId": thread_id or f"thread{len(self._emails) + 1:03d}",
            "labelIds": ["SENT"],
        }

    def batch_modify_messages(
        self,
        message_ids: list[str],
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Modify multiple messages in a single API call (mock)."""
        logger.info(
            f"[mock_gmail] Batch modifying {len(message_ids)} messages: "
            f"add={add_labels}, remove={remove_labels}"
        )

        # Update labels on mock emails
        for email in self._emails:
            if email["id"] in message_ids:
                if add_labels:
                    for label in add_labels:
                        if label not in email["labels"]:
                            email["labels"].append(label)
                if remove_labels:
                    email["labels"] = [
                        label for label in email["labels"] if label not in remove_labels
                    ]

        return {"success": True, "modified_count": len(message_ids)}

