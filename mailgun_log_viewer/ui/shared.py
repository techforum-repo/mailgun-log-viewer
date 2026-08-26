from __future__ import annotations

"""State, navigation, and small widgets shared across every page in
mailgun_log_viewer/ui/*. Page-specific rendering stays in that page's own
module.
"""

import streamlit as st

from ..config import LOG_RETENTION_DAYS, settings
from ..errors import friendly_error

PAGE_NAMES = ["Events", "Settings", "Diagnostics"]

CUSTOM_CSS = """<style>
.block-container{max-width:1450px;padding-top:1.35rem}
.hero{padding:1.1rem 1.35rem;border:1px solid #ddd;border-radius:16px;margin-bottom:1rem}
[data-testid=stMetric]{border:1px solid #ddd;padding:1rem;border-radius:14px}
.badge{padding:.25rem .55rem;border:1px solid #ccc;border-radius:999px;font-size:.8rem}
</style>"""

DEFAULT_STATE = {
    "events_rows": None,
    # events_columns is deliberately NOT pre-populated here: it's a widget
    # key (the Columns multiselect in events_page.py) with its own
    # `default=`. Pre-setting it to any value — None included — makes
    # Streamlit use that stored value instead of the widget's `default=` on
    # first render; None specifically crashes the widget outright
    # ("'NoneType' object is not iterable") since a multiselect's backing
    # value must be a list. Leaving the key absent lets `default=` apply
    # normally the first time, same as every other filter widget on that
    # page.
    #
    # Fixed per session so repeated "Fetch" clicks in mock mode return a
    # stable dataset instead of reshuffling on every rerun.
    "mock_seed": 20260826,
}


def init_session_state() -> None:
    for key, value in DEFAULT_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = value


def query_domains() -> list[str]:
    """Every domain a fetch queries — no per-session "active domain" picker
    any more. Previously the sidebar restricted a session to one
    MAILGUN_DOMAINS entry at a time, which made the Events page's sender-
    domain contains/not-contains filter redundant (it could never narrow
    anything the sidebar hadn't already fixed). Now every configured domain
    is always queried and merged, so that filter does real work when an
    account has more than one domain — mock mode mirrors this with its own
    fixed list."""
    return settings.domain_list or (["mock.example.com"] if settings.mock_mode else [])


def render_sidebar() -> str:
    with st.sidebar:
        st.markdown("## 📬 Mailgun Log Viewer")
        page = st.radio("Navigation", PAGE_NAMES, label_visibility="collapsed", key="navigation")
        st.divider()
        mode = "Mock / demo data" if settings.mock_mode else "Live"
        st.markdown(f"<span class='badge'>{mode}</span>", unsafe_allow_html=True)
        if settings.mock_mode:
            st.caption("Set MOCK_MODE=false in .env once a Mailgun API key and domain are filled in.")
        st.divider()
        domains = query_domains()
        st.caption("Querying domain(s): **" + (", ".join(domains) if domains else "(none configured)") + "**")
        st.caption("Edit MAILGUN_DOMAINS in .env to add or remove one.")
        st.caption(f"Region: **{settings.mailgun_region.upper()}** — events retained roughly the last **{LOG_RETENTION_DAYS} days**.")
    return page


def render_hero() -> None:
    st.markdown(
        "<div class='hero'><h1>Mailgun Log Viewer</h1>"
        "<p>Query Mailgun's Events API with sender/domain/status/date filters and pick exactly the columns you need.</p></div>",
        unsafe_allow_html=True,
    )


def render_friendly_error(exc: Exception, *, key: str, context: str = "") -> bool:
    """Plain-language error box instead of a raw traceback. Returns True if
    the user clicked Retry, so the caller can re-run the action inline."""
    info = friendly_error(exc)
    with st.container(border=True):
        st.error(f"**{info.title}**")
        if context:
            st.caption(context)
        if info.reasons:
            st.markdown("Possible reasons:\n\n" + "\n".join(f"- {reason}" for reason in info.reasons))
        with st.expander("Technical details"):
            st.code(str(exc) or "(no message)")
        if info.retryable:
            return st.button("Retry", key=key)
    return False


def fetch_button(label: str, key: str) -> bool:
    return st.button(f"🔍 {label}", key=key, type="primary")
