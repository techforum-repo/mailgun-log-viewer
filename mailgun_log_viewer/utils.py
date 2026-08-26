from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Coroutine, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Bridge an async client call into Streamlit's sync page code."""
    return asyncio.run(coro)


def safe_dict(value: Any) -> dict[str, Any]:
    """Coerce a value a parser assumed would be a nested object into an
    empty dict when it isn't one, instead of leaving a landmine for the
    next `.get()` call. Mailgun's event schema varies by event type
    (a `failed` event carries `delivery-status` fields a `stored` event
    doesn't), so every nested `.get()` in clients/events.py goes through
    this rather than a bare `or {}` — `or {}` alone doesn't protect against
    a field that's present but holds an unexpected type."""
    return value if isinstance(value, dict) else {}


def get_path(obj: Any, dotted_path: str) -> Any:
    """Look up a dotted path (e.g. "message.headers.subject") through nested
    dicts, returning "" if any segment is missing or not a dict. Powers the
    column-selection feature in filters.py: the UI lets a user pick exactly
    the dotted fields they want (per the columns Mailgun's own event JSON
    exposes) without a bespoke accessor per field."""
    current = obj
    for segment in dotted_path.split("."):
        if not isinstance(current, dict):
            return ""
        current = current.get(segment, "")
    return current if current is not None else ""


# Mailgun's `message.headers.from`/`to` are raw RFC 5322 header values, e.g.
# `"Jane Doe <jane@example.com>"` — not a bare address. This pulls the
# address (and from it, the domain) whether or not a display name is
# present, for the "sender domain contains/not contains" filter.
_ADDR_RE = re.compile(r"<([^<>]+)>")


def extract_email_address(header_value: Any) -> str:
    text = str(header_value or "").strip()
    if not text:
        return ""
    match = _ADDR_RE.search(text)
    return (match.group(1) if match else text).strip().lower()


def extract_domain(header_value: Any) -> str:
    address = extract_email_address(header_value)
    return address.rsplit("@", 1)[-1] if "@" in address else ""


# Leading characters that make Excel/Sheets/Numbers interpret a CSV cell as a
# formula instead of literal text (CSV/formula injection, OWASP-recognized).
_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value: Any) -> Any:
    """Neutralize CSV/formula injection: a cell starting with =, +, -, @, or a
    tab is prefixed with a single quote so spreadsheet apps treat it as
    literal text instead of executing it as a formula when a downstream user
    opens the export (subjects and display names in these events are free
    text someone else typed, not text this app controls)."""
    if not isinstance(value, str) or not value:
        return value
    return f"'{value}" if value[0] in _FORMULA_TRIGGER_CHARS else value


def safe_csv(df: pd.DataFrame, *, index: bool = False) -> bytes:
    """CSV export with formula-injection protection applied to every text
    column, encoded as UTF-8 with a BOM (`utf-8-sig`) so Excel doesn't
    mis-detect the encoding and mangle a non-ASCII subject line or display
    name. Returns bytes (not str) so st.download_button() passes them
    through unchanged instead of re-encoding and losing the BOM."""
    sanitized = df.copy()
    for column in sanitized.columns:
        if sanitized[column].dtype == object:
            sanitized[column] = sanitized[column].map(sanitize_csv_cell)
    return sanitized.to_csv(index=index).encode("utf-8-sig")


def parse_list(value: str) -> list[str]:
    """Split a comma-separated text-input value into a trimmed, non-empty
    list — how every multi-value filter (From, To, Sender domain) on the
    Events page accepts more than one address/domain at once, OR'd
    together, without needing a dedicated multi-value widget."""
    return [item.strip() for item in value.split(",") if item.strip()]


def local_now(tz_name: str) -> datetime:
    """The current time in the given IANA zone — same fallback-to-UTC
    behavior as to_utc(), for the Events page's date pickers to default to
    "today" in whatever timezone the user has selected rather than UTC's
    today (which can be a different calendar date near midnight)."""
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = timezone.utc
    return datetime.now(tz)


def to_utc(local_dt: datetime, tz_name: str) -> datetime:
    """Interpret a naive datetime as wall-clock time in the given IANA zone
    (e.g. "America/Chicago") and convert it to a UTC-aware datetime.

    Exists because Mailgun's Events API and this app's internal EventFilters
    are always UTC, but a calendar day in Central time isn't a calendar day
    in UTC — Central midnight is 05:00 or 06:00 UTC depending on whether
    CDT or CST is in effect. Using zoneinfo (stdlib, no extra dependency)
    instead of a fixed offset means that DST switch is handled correctly
    without this app needing to track when it happens.

    Falls back to treating `local_dt` as already UTC if `tz_name` isn't a
    recognized IANA zone (e.g. a typo in .env) — better than crashing the
    Events page over a bad timezone string, at the cost of silently not
    doing the conversion; the Settings page shows the configured value so a
    typo is visible there."""
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = timezone.utc
    return local_dt.replace(tzinfo=tz).astimezone(timezone.utc)


def local_hour_bucket(epoch_seconds: float, tz_name: str) -> str:
    """The hour-bucket label (e.g. "2026-08-26 14:00") for a Unix timestamp,
    in the given IANA zone — same fallback-to-UTC behavior as to_utc()/
    local_now(). Powers the Events page's "volume by sender, hourly" chart
    so its buckets line up with whatever timezone the date range itself is
    being viewed in, rather than always bucketing in UTC."""
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = timezone.utc
    return datetime.fromtimestamp(epoch_seconds, tz=tz).strftime("%Y-%m-%d %H:00")


def harden_file_permissions(path: Path, *, mode: int = 0o600) -> None:
    """Restrict a local data file (SQLite DB, log file, .env) to the owning
    user only. Defaults to 0o600; pass mode=0o700 for a directory.

    POSIX only — chmod doesn't provide equivalent access control on Windows,
    so this is a no-op there. Best-effort: never raises, so it can't block
    app startup or logging."""
    if os.name == "nt":
        return
    try:
        path.chmod(mode)
    except OSError:
        pass
