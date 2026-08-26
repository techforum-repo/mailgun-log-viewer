from __future__ import annotations

import streamlit as st

from ..config import LOG_RETENTION_DAYS, settings


def _mask(value: str) -> str:
    if not value:
        return "(not set)"
    return f"{value[:4]}{'•' * max(len(value) - 8, 4)}{value[-4:]}" if len(value) > 8 else "•" * len(value)


def render() -> None:
    st.markdown("### Settings")
    st.caption("Read-only view of the configuration loaded from `.env` — edit that file and restart the app to change any of this.")

    st.markdown("#### Mailgun")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Mode", "Mock / demo data" if settings.mock_mode else "Live")
        st.metric("Region", settings.mailgun_region.upper())
    with col2:
        st.metric("Configured", "Yes" if settings.mailgun_configured else "No")
        st.metric("Retention assumption", f"{LOG_RETENTION_DAYS} days")

    st.text_input("API key", value=_mask(settings.mailgun_api_key), disabled=True)
    st.text_input("Base URL", value=settings.mailgun_base_url, disabled=True)
    st.text_area("Configured domains", value="\n".join(settings.domain_list) or "(none)", disabled=True, height=80)

    if settings.mock_mode:
        st.info("MOCK_MODE=true — every page shows generated sample events, no Mailgun call is ever made.")
    elif not settings.mailgun_configured:
        st.warning("MOCK_MODE=false but MAILGUN_API_KEY / MAILGUN_DOMAINS are incomplete — live calls will fail. See `.env.example`.")

    st.markdown("#### Networking")
    col3, col4, col5 = st.columns(3)
    col3.metric("HTTP timeout", f"{settings.http_timeout:.0f}s")
    col4.metric("Requests/sec", f"{settings.requests_per_second:g}")
    col5.metric("Events page size", settings.events_page_size)
    st.caption(f"Max events per query: **{settings.max_events_per_query}** — a hard ceiling per \"Fetch\" click across all pages/statuses, to bound how much one click can pull.")
