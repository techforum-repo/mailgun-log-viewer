from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from .utils import harden_file_permissions

# Resolved relative to the project root as long as the app is started from
# there (true for start-unix.sh / start-windows.bat / `streamlit run app.py`
# from a checkout) — same convention as logging_setup.py's LOG_PATH.
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

_REGION_BASE_URLS = {
    "us": "https://api.mailgun.net/v3",
    "eu": "https://api.eu.mailgun.net/v3",
}

# Mailgun's Events API only retains events for a limited window — 5 days on
# the free tier, up to 30 on paid plans depending on the account. This
# account's is 15; not something the API itself reports back, so it's a
# plain constant the UI uses to pre-fill "begin" and to explain an
# unexpectedly empty result, rather than a config knob someone needs to
# tune. Change it here if the account's plan changes.
LOG_RETENTION_DAYS = 15


class Settings(BaseSettings):
    app_env: str = "development"

    # Mock mode serves realistic sample events so the Events page is fully
    # explorable before any Mailgun credential exists. Flips to live once
    # mailgun_configured is true, unless forced with MOCK_MODE=true.
    mock_mode: bool = True

    # --- Mailgun credential ---------------------------------------------------
    # Private API key from Settings -> API Keys in the Mailgun dashboard.
    # Sent as HTTP Basic Auth ("api", this key) — see auth.py.
    mailgun_api_key: str = ""
    # Comma-separated sending domain(s) this app queries — every one of them
    # is fetched and merged on every "Fetch" click (see ui/shared.py's
    # query_domains()), e.g. "mail.example.com,updates.example.com".
    mailgun_domains: str = ""
    # "us" or "eu" — Mailgun's two API regions use entirely different base
    # URLs and a domain only exists in the one it was created in. Get this
    # wrong and every call 401s even with a correct key, which looks
    # identical to a bad key — see errors.py's guidance for that exact
    # ambiguity.
    mailgun_region: str = "us"

    # IANA timezone the Events page's date-range picker is interpreted in —
    # NOT the same as MAILGUN_REGION above (that's which Mailgun API to
    # hit) and NOT the same as whatever display timezone your Mailgun
    # account's own dashboard is set to (that's cosmetic to Mailgun's web
    # UI only, and this app never reads it). This purely controls what "the
    # 26th" means when picked in the Events page: midnight-to-midnight in
    # this zone, converted to UTC (via utils.to_utc, DST-aware) before
    # being sent to Mailgun or compared against event timestamps.
    report_timezone: str = "America/Chicago"

    http_timeout: float = 30.0
    # Mailgun doesn't publish one universal per-key rate limit; this is a
    # conservative default to keep a multi-page events pull well clear of
    # any throttling. Tunable from the Settings page without a restart.
    requests_per_second: float = 5.0

    # Mailgun's events API paginates at up to 300 items/page via a `next`
    # cursor URL. These two bound one "Fetch" click: page size per request,
    # and a hard ceiling on total events pulled across all pages so a wide
    # date range with a busy domain can't turn one click into an unbounded
    # crawl.
    events_page_size: int = 300
    max_events_per_query: int = 3000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def mailgun_configured(self) -> bool:
        return bool(self.mailgun_api_key and self.domain_list)

    @property
    def domain_list(self) -> list[str]:
        return [d.strip() for d in self.mailgun_domains.split(",") if d.strip()]

    @property
    def mailgun_base_url(self) -> str:
        return _REGION_BASE_URLS.get(self.mailgun_region.strip().lower(), _REGION_BASE_URLS["us"])


settings = Settings()


def harden_env_file() -> None:
    """Restrict .env (holds the Mailgun API key) to the owning user only —
    mirrors how logging_setup.py hardens the log file. Called explicitly
    from app.py's startup, not at import time, so importing this module
    never has filesystem side effects on its own."""
    if ENV_PATH.exists():
        harden_file_permissions(ENV_PATH)
