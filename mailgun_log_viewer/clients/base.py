from __future__ import annotations

"""Shared HTTP plumbing for Mailgun API calls: auth attachment, request
pacing, and uniform error normalization. events.py subclasses
BaseMailgunClient and only adds endpoint methods.
"""

import threading
import time
from typing import Any

import httpx

from ..auth import basic_auth
from ..config import settings
from ..errors import MailgunRateLimitError


def _parse_retry_after(value: str | None) -> float | None:
    """Mailgun sends Retry-After as seconds, not an HTTP-date."""
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


class RequestPacer:
    """Enforces a minimum spacing between outgoing requests for one client
    instance. Scoped per client instance (not global) so a UI session
    pulling events doesn't have to share a rate budget with anything else
    that might one day use this app's HTTP plumbing."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_allowed_at = 0.0

    def wait(self) -> None:
        rps = settings.requests_per_second
        if rps <= 0:
            return
        min_interval = 1.0 / rps
        with self._lock:
            now = time.monotonic()
            delay = self._next_allowed_at - now
            if delay > 0:
                time.sleep(delay)
                now = time.monotonic()
            self._next_allowed_at = now + min_interval


class BaseMailgunClient:
    """Not instantiated directly — see events.py."""

    def __init__(self) -> None:
        self._pacer = RequestPacer()

    def _new_http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=settings.http_timeout, auth=basic_auth(), trust_env=True)

    async def _request(self, http: httpx.AsyncClient, method: str, url: str, **kwargs: Any) -> Any:
        self._pacer.wait()
        try:
            response = await http.request(method, url, **kwargs)
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            return response.json() if response.content else {}
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to Mailgun. Check network/proxy/firewall. Endpoint: {url}") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"Mailgun request timed out. Endpoint: {url}") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            if exc.response.status_code == 429:
                retry_after = _parse_retry_after(exc.response.headers.get("Retry-After"))
                raise MailgunRateLimitError(f"Mailgun returned HTTP 429: {detail}", retry_after=retry_after) from exc
            raise RuntimeError(f"Mailgun returned HTTP {exc.response.status_code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Mailgun request failed: {exc}. Endpoint: {url}") from exc

    async def get(self, http: httpx.AsyncClient, url: str, **kwargs: Any) -> Any:
        return await self._request(http, "GET", url, **kwargs)

    async def test_connection(self) -> bool:
        """Overridden per client with a cheap, harmless read call."""
        raise NotImplementedError
