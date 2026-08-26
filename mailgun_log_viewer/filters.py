from __future__ import annotations

"""Filter model, Mailgun query building, and column extraction — the
business-logic layer between clients/events.py (raw HTTP) and ui/events_page.py
(the form). Framework-agnostic (no Streamlit import) so it's unit-testable on
its own.

Mailgun's Events API only supports a handful of filters server-side: event
type (`event`), a date window (`begin`/`end`/`ascending`), and an exact
recipient address (`recipient`). It has no "not equals", no "contains", and
no filter at all on the sender address or subject. This module's job is to
use what Mailgun *does* support to narrow the pull as much as possible, then
apply everything else (sender not-equals, domain not-contains, subject
contains, ...) client-side against the events already fetched.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Any

import httpx
import pandas as pd

from .clients import mock as mock_client
from .clients.events import EventsClient
from .config import settings
from .utils import extract_domain, extract_email_address, get_path

# Every event type Mailgun's Events API recognizes — used to populate the
# status multiselect. https://documentation.mailgun.com/en/latest/api-events.html#event-types
EVENT_TYPES = [
    "accepted", "delivered", "failed", "opened", "clicked", "unsubscribed",
    "complained", "stored", "rejected", "list_member_uploaded", "list_member_upload_error",
]

# Dotted path -> column shown in the UI's picker. "@timestamp" is not a real
# Mailgun field (there is no literal "@timestamp" key in the event JSON) —
# it's a computed column, Mailgun's top-level `timestamp` (Unix epoch
# seconds) rendered as ISO 8601, kept under this name because that's the
# label asked for and it reads naturally next to the other dotted paths.
COLUMN_OPTIONS: dict[str, str] = {
    "@timestamp": "Event time (from Mailgun's `timestamp` field)",
    "event": "Event type (delivered, failed, opened, ...)",
    "message.headers.from": "From header",
    "message.headers.to": "To header",
    "message.headers.subject": "Subject header",
    "message.headers.message-id": "Message-Id header",
    "recipient": "Recipient address",
    "recipient-domain": "Recipient domain",
    "envelope.sender": "Envelope sender",
    "delivery-status.description": "Delivery status description",
    "delivery-status.code": "Delivery status code",
    "tags": "Tags",
    "id": "Mailgun event id",
}

DEFAULT_COLUMNS = ["@timestamp", "message.headers.from", "message.headers.subject", "message.headers.to"]


@dataclass
class EventFilters:
    statuses: list[str] = field(default_factory=list)  # empty = every event type
    begin: datetime | None = None
    end: datetime | None = None
    ascending: bool = False

    # Sender — no native Mailgun filter; always applied client-side against
    # message.headers.from.
    from_equals: str = ""
    from_not_equals: str = ""
    domain_contains: str = ""
    domain_not_contains: str = ""

    # Subject — no native filter either.
    subject_contains: str = ""

    # Recipient — `to_equals` maps to Mailgun's native `recipient` param
    # (an exact match, cheap to push server-side); `to_contains` has no
    # native equivalent and is applied client-side.
    to_equals: str = ""
    to_contains: str = ""


def _native_params(filters: EventFilters, status: str | None) -> dict[str, Any]:
    """Query params Mailgun itself understands, for one status value (or
    None for "every type"). Multiple selected statuses become multiple
    calls — see fetch_filtered_events — because the API takes a single
    `event` value per request."""
    params: dict[str, Any] = {
        "limit": settings.events_page_size,
        "ascending": "yes" if filters.ascending else "no",
    }
    if filters.begin is not None:
        params["begin"] = format_datetime(filters.begin)
    if filters.end is not None:
        params["end"] = format_datetime(filters.end)
    if status:
        params["event"] = status
    if filters.to_equals.strip():
        params["recipient"] = filters.to_equals.strip()
    return params


def _passes_client_filters(event: dict[str, Any], filters: EventFilters) -> bool:
    from_header = get_path(event, "message.headers.from")
    to_header = str(get_path(event, "message.headers.to") or "")
    subject = str(get_path(event, "message.headers.subject") or "")
    from_addr = extract_email_address(from_header)
    domain = extract_domain(from_header)

    if filters.from_equals.strip() and from_addr != filters.from_equals.strip().lower():
        return False
    if filters.from_not_equals.strip() and from_addr == filters.from_not_equals.strip().lower():
        return False
    if filters.domain_contains.strip() and filters.domain_contains.strip().lower() not in domain:
        return False
    if filters.domain_not_contains.strip() and filters.domain_not_contains.strip().lower() in domain:
        return False
    if filters.subject_contains.strip() and filters.subject_contains.strip().lower() not in subject.lower():
        return False
    if filters.to_contains.strip() and filters.to_contains.strip().lower() not in to_header.lower():
        return False
    return True


async def fetch_filtered_events(
    client: EventsClient, http: httpx.AsyncClient, domain: str, filters: EventFilters
) -> list[dict[str, Any]]:
    """One call per selected status (or one call total if none selected),
    each already capped by settings.max_events_per_query — then merged,
    de-duplicated by Mailgun's event id (only possible if the same event
    somehow matched two status calls, which shouldn't happen since `event`
    is a single value per item, but cheap to guard), truncated to the
    overall cap again since multiple status calls each apply their own, and
    finally narrowed by every client-side-only condition."""
    statuses = filters.statuses or [None]
    merged: dict[str, dict[str, Any]] = {}
    for status in statuses:
        params = _native_params(filters, status)
        for event in await client.fetch_events(http, domain, params):
            event_id = str(event.get("id") or len(merged))
            merged.setdefault(event_id, event)

    events = list(merged.values())[: settings.max_events_per_query]
    return [e for e in events if _passes_client_filters(e, filters)]


def _matches_status_and_date(event: dict[str, Any], filters: EventFilters) -> bool:
    """Mock mode has no server to push `event`/`begin`/`end` to, so those
    two native-in-live conditions are applied here instead — kept separate
    from `_passes_client_filters` so that function stays an exact mirror of
    what's genuinely client-side against a live response."""
    if filters.statuses and event.get("event") not in filters.statuses:
        return False
    timestamp = event.get("timestamp")
    if filters.begin is not None and timestamp is not None and timestamp < filters.begin.timestamp():
        return False
    if filters.end is not None and timestamp is not None and timestamp > filters.end.timestamp():
        return False
    if filters.to_equals.strip() and str(event.get("recipient") or "").lower() != filters.to_equals.strip().lower():
        return False
    return True


def fetch_mock_events(domain: str, filters: EventFilters, *, seed: int | None = None) -> list[dict[str, Any]]:
    events = mock_client.generate_events(domain, count=settings.max_events_per_query, seed=seed)
    return [e for e in events if _matches_status_and_date(e, filters) and _passes_client_filters(e, filters)]


async def fetch_events(domain: str, filters: EventFilters, *, mock_seed: int | None = None) -> list[dict[str, Any]]:
    """Single entry point ui/events_page.py calls — dispatches to mock or
    live data depending on settings.mock_mode so the page itself never
    branches on it."""
    if settings.mock_mode:
        return fetch_mock_events(domain, filters, seed=mock_seed)
    client = EventsClient()
    async with client._new_http_client() as http:  # noqa: SLF001 (same package)
        return await fetch_filtered_events(client, http, domain, filters)


def format_epoch(value: Any) -> str:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return ""


def extract_row(event: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for column in columns:
        if column == "@timestamp":
            row[column] = format_epoch(event.get("timestamp"))
            continue
        value = get_path(event, column)
        row[column] = ", ".join(str(v) for v in value) if isinstance(value, list) else value
    return row


def events_to_dataframe(events: list[dict[str, Any]], columns: list[str]) -> pd.DataFrame:
    if not columns:
        columns = DEFAULT_COLUMNS
    return pd.DataFrame([extract_row(e, columns) for e in events], columns=columns)
