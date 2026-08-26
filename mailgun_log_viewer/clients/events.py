from __future__ import annotations

"""Mailgun Events API client.

Docs: https://documentation.mailgun.com/docs/mailgun/api-reference/openapi-final/tag/Events/

GET /<domain>/events returns a page of events plus a `paging.next` cursor
URL; there is no "give me everything matching X" single call, so
`fetch_events()` follows `next` itself, capped by
`settings.max_events_per_query` so a wide date range on a busy domain can't
turn one UI click into an unbounded crawl.

Only a subset of what this app's Events page lets someone ask for is
actually a *server-side* Mailgun query parameter: `event` (status),
`begin`/`end`/`ascending` (date range), and `recipient` (exact address
match). Mailgun's API has no "not equals" or "not contains" operator, and
no filter at all on the sender address or subject — those are
`message.headers.*` fields Mailgun returns per-event but never lets you
filter by server-side. `filters.py` is where that gap is closed: it builds
the server-side query from what Mailgun supports, then applies the
remaining conditions (sender not-equals, domain not-contains, subject/to
contains, ...) client-side against the page(s) already fetched.
"""

from typing import Any
from urllib.parse import urlencode

import httpx

from ..config import settings
from .base import BaseMailgunClient


class EventsClient(BaseMailgunClient):
    def _events_url(self, domain: str) -> str:
        return f"{settings.mailgun_base_url}/{domain}/events"

    async def fetch_page(self, http: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        data = await self.get(http, url, params=params)
        return data if isinstance(data, dict) else {}

    async def fetch_events(
        self,
        http: httpx.AsyncClient,
        domain: str,
        params: dict[str, Any],
        *,
        max_events: int | None = None,
    ) -> list[dict[str, Any]]:
        """Follows `paging.next` until either Mailgun stops returning items
        or `max_events` (defaults to settings.max_events_per_query) is hit.
        Mailgun's `next` URL is already fully-formed (includes its own query
        string) — later pages are fetched by URL alone, params only apply to
        the first request."""
        cap = max_events if max_events is not None else settings.max_events_per_query
        collected: list[dict[str, Any]] = []
        url = self._events_url(domain)
        page_params: dict[str, Any] | None = params
        while url and len(collected) < cap:
            page = await self.fetch_page(http, url, page_params)
            items = page.get("items", [])
            if not isinstance(items, list) or not items:
                break
            collected.extend(items)
            url = ((page.get("paging") or {}).get("next")) or ""
            page_params = None  # `next` already carries the full query string
        return collected[:cap]

    async def test_connection(self) -> bool:
        """Cheapest possible read: one event, no filters, on the first
        configured domain."""
        if not settings.domain_list:
            raise RuntimeError("Mailgun is not configured — MAILGUN_DOMAINS is missing from .env.")
        async with self._new_http_client() as http:
            await self.fetch_page(http, self._events_url(settings.domain_list[0]), {"limit": 1})
        return True


def build_query_string(params: dict[str, Any]) -> str:
    """Exposed for the UI's "show the equivalent Mailgun API call" expander
    — httpx builds this internally for the actual request, but nothing else
    here otherwise renders it back for a user to see or copy."""
    return urlencode({k: v for k, v in params.items() if v not in (None, "")}, doseq=True)
