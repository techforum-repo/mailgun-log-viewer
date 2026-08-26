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
    "events_columns": None,
    # Fixed per session so repeated "Fetch" clicks in mock mode return a
    # stable dataset instead of reshuffling on every rerun.
    "mock_seed": 20260826,
}


def init_session_state() -> None:
    for key, value in DEFAULT_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get_active_domain() -> str:
    """The Mailgun sending domain every page should query — the sidebar
    switcher's current value, defaulting to the first entry in
    MAILGUN_DOMAINS before the switcher has been touched. Session-only:
    never writes back to .env."""
    return st.session_state.get("active_domain") or (settings.domain_list[0] if settings.domain_list else "")


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
        domain_options = settings.domain_list or (["(no domain configured)"] if not settings.mock_mode else ["mock.example.com"])
        st.session_state.setdefault("active_domain", domain_options[0])
        if st.session_state["active_domain"] not in domain_options:
            domain_options = [st.session_state["active_domain"], *domain_options]
        st.selectbox("Sending domain", domain_options, key="active_domain", help="Which Mailgun domain's event log to query.")
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
