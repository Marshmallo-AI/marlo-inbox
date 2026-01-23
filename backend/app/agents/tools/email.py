from __future__ import annotations

"""
Gmail tools for marlo-inbox agent.

This file will be implemented by Agent 2.
See AGENT_2_PROMPT.md for implementation details.
"""

from langchain_core.tools import StructuredTool
from pydantic import BaseModel


# Placeholder schemas - Agent 2 will implement properly
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


# Placeholder implementations - Agent 2 will implement properly
async def _list_emails(max_results: int = 10):
    raise NotImplementedError("To be implemented by Agent 2")


async def _get_email(email_id: str):
    raise NotImplementedError("To be implemented by Agent 2")


async def _search_emails(query: str, max_results: int = 10):
    raise NotImplementedError("To be implemented by Agent 2")


async def _draft_reply(email_id: str, instructions: str):
    raise NotImplementedError("To be implemented by Agent 2")


async def _send_email(to: str, subject: str, body: str, reply_to_id: str | None = None):
    raise NotImplementedError("To be implemented by Agent 2")


# Tool definitions
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
