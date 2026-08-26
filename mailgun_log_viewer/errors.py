from __future__ import annotations

"""Turn raw exception text into a title + a short list of likely causes.

Kept framework-agnostic (no Streamlit import) so it stays unit-testable; the
UI wraps this with a small renderer in ui/shared.py.
"""

from dataclasses import dataclass, field


class MailgunRateLimitError(RuntimeError):
    """Raised specifically for Mailgun HTTP 429 responses.

    Carries the `Retry-After` header (seconds) when Mailgun sends one, so
    retry.call_with_retry can wait exactly as long as Mailgun asked instead
    of guessing with blind exponential backoff. `retry_after` is None when
    the header was absent or unparsable, in which case the caller falls back
    to the normal backoff schedule.
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True)
class FriendlyError:
    title: str
    reasons: list[str] = field(default_factory=list)
    retryable: bool = True


_CONNECTION_REASONS = [
    "No internet connectivity, or a corporate proxy/firewall is blocking the request",
    "Mailgun is temporarily unavailable",
]
_TIMEOUT_REASONS = [
    "Mailgun is slow to respond right now",
    "The date range covers more events than usual",
]
_AUTH_REASONS = [
    "MAILGUN_API_KEY is wrong, revoked, or was pasted with extra whitespace",
    # The single most common Mailgun-specific gotcha: a correct key against
    # the wrong region's base URL 401s identically to a wrong key, because a
    # domain (and the key scoped to its account) only exists in the region
    # it was created in. This app's own base URL choice is MAILGUN_REGION,
    # not something Mailgun's error body ever names for you.
    "MAILGUN_REGION is set to the wrong region for this domain (a US-created domain "
    "401s against api.eu.mailgun.net and vice versa) — check the domain's region on "
    "Mailgun's Sending → Domains page",
    "The API key belongs to a different Mailgun account than the domain being queried",
]
_NOT_FOUND_REASONS = [
    "The domain isn't in this Mailgun account, or is misspelled in MAILGUN_DOMAINS",
    "The domain exists but is in the other region (see MAILGUN_REGION above)",
]
_CONFIG_REASONS = [
    "MAILGUN_API_KEY or MAILGUN_DOMAINS is missing from .env",
    "The app was not restarted after .env was last edited",
]


def friendly_error(exc: BaseException) -> FriendlyError:
    message = str(exc).strip()
    lowered = message.lower()

    if "not configured" in lowered:
        return FriendlyError("Mailgun is not configured", _CONFIG_REASONS, retryable=False)
    if "cannot connect" in lowered:
        return FriendlyError("Mailgun connection failed", _CONNECTION_REASONS)
    if "timed out" in lowered or "timeout" in lowered:
        return FriendlyError("Mailgun request timed out", _TIMEOUT_REASONS)
    if "http 401" in lowered or "http 403" in lowered:
        return FriendlyError("Mailgun rejected the request (unauthorized)", _AUTH_REASONS, retryable=False)
    if "http 404" in lowered:
        return FriendlyError("Domain not found", _NOT_FOUND_REASONS, retryable=False)
    if "http 429" in lowered:
        return FriendlyError(
            "Mailgun is rate-limiting requests",
            [
                "Too many requests were sent in a short period. Wait a moment and retry.",
                "Lower \"Requests/sec\" on the Settings page.",
            ],
        )
    if "http 5" in lowered and "mailgun returned http 5" in lowered:
        return FriendlyError("Mailgun returned a server error", ["Mailgun is having a temporary issue on their end."])

    return FriendlyError("Something went wrong", [message] if message else ["An unexpected error occurred."])
