from __future__ import annotations

"""Realistic sample events so the Events page is fully explorable before any
Mailgun credential exists — same "mock-first" convention as the sibling
Adobe tools' clients/mock.py. Shaped to match Mailgun's real event JSON
(https://documentation.mailgun.com/en/latest/api-events.html#event-structure)
closely enough that filters.py's column extraction and client-side filters
exercise exactly the same code path as a live response.
"""

import random
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import LOG_RETENTION_DAYS

_SENDERS = [
    ("Acme Notifications", "notifications@acme-mail.com"),
    ("Acme Billing", "billing@acme-mail.com"),
    ("Beta Corp Marketing", "marketing@betacorp.io"),
    ("Beta Corp Support", "support@betacorp.io"),
    ("Gamma Alerts", "alerts@gamma-systems.net"),
]
_RECIPIENTS = [
    "jane.doe@example.com", "john.smith@example.org", "maria.garcia@example.net",
    "li.wei@example.com", "sam.patel@example.org",
]
_SUBJECTS = [
    "Your invoice is ready", "Weekly digest", "Action required: verify your email",
    "New sign-in detected", "Your order has shipped", "Password reset requested",
    "Monthly newsletter", "Payment failed", "Welcome aboard!",
]
_TAGS = ["welcome", "billing", "marketing", "transactional"]
# Roughly mirrors a healthy sending domain's real event mix — mostly
# delivered, a small tail of engagement and failure events.
_EVENT_WEIGHTS = [
    ("delivered", 55), ("opened", 15), ("clicked", 8), ("accepted", 10),
    ("failed", 6), ("stored", 3), ("complained", 1), ("unsubscribed", 2),
]
_FAILURE_REASONS = ["Mailbox does not exist", "Message rejected by recipient server", "Connection timed out"]


def _pick_event_type(rng: random.Random) -> str:
    population = [e for e, _ in _EVENT_WEIGHTS]
    weights = [w for _, w in _EVENT_WEIGHTS]
    return rng.choices(population, weights=weights, k=1)[0]


def generate_events(domain: str, count: int = 250, seed: int | None = None) -> list[dict[str, Any]]:
    """`seed` is fixed by the caller (events_page.py) per Streamlit session
    so repeated "Fetch" clicks in mock mode show a stable dataset instead of
    reshuffling on every rerun — a real Mailgun account behaves the same way
    (the same query returns the same events) and mock mode should feel like
    that, not like random noise each click."""
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    events = []
    for i in range(count):
        name, addr = rng.choice(_SENDERS)
        recipient = rng.choice(_RECIPIENTS)
        event_type = _pick_event_type(rng)
        # Spread across the account's actual retention window, not further
        # back — mirrors what a real query could ever return.
        ts = now - timedelta(seconds=rng.uniform(0, LOG_RETENTION_DAYS * 86400))
        event: dict[str, Any] = {
            "id": f"mock-{i:06d}",
            "timestamp": ts.timestamp(),
            "event": event_type,
            "recipient": recipient,
            "recipient-domain": recipient.split("@", 1)[-1],
            "envelope": {"sender": addr, "transport": "smtp"},
            "message": {
                "headers": {
                    "from": f"{name} <{addr}>",
                    "to": recipient,
                    "subject": rng.choice(_SUBJECTS),
                    "message-id": f"<{rng.randrange(10**12, 10**13)}.{i}@{domain}>",
                },
                "size": rng.randint(800, 25000),
            },
            "tags": rng.sample(_TAGS, k=rng.randint(0, 2)),
        }
        if event_type == "failed":
            event["severity"] = rng.choice(["permanent", "temporary"])
            event["delivery-status"] = {"description": rng.choice(_FAILURE_REASONS), "code": rng.choice([550, 421, 450])}
        events.append(event)
    events.sort(key=lambda e: e["timestamp"], reverse=True)
    return events
