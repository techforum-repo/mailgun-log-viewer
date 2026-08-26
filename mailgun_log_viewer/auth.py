from __future__ import annotations

"""Mailgun authentication: HTTP Basic Auth with the fixed username "api" and
the account's private API key as the password — no token issuance or
refresh, unlike the OAuth Server-to-Server flow this module's counterpart
handles in the sibling Adobe tools. Kept as its own module anyway, matching
their shape, so every client still gets its auth the same way (import from
here) rather than each one building the tuple inline.
"""

import httpx

from .config import settings


def basic_auth() -> httpx.BasicAuth:
    if not settings.mailgun_api_key:
        raise RuntimeError("Mailgun is not configured — MAILGUN_API_KEY is missing from .env.")
    return httpx.BasicAuth("api", settings.mailgun_api_key)
