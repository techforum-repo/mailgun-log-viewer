from __future__ import annotations

import streamlit as st

from ..clients.events import EventsClient
from ..config import settings
from ..logging_setup import LOG_PATH
from ..utils import run_async
from .shared import render_friendly_error


def render() -> None:
    st.markdown("### Diagnostics")

    st.markdown("#### Connection check")
    if settings.mock_mode:
        st.info("MOCK_MODE=true — there's no live Mailgun connection to check. Set MOCK_MODE=false in `.env` first.")
    else:
        if st.button("Test connection", type="primary"):
            try:
                run_async(EventsClient().test_connection())
                st.session_state["_diag_result"] = ("ok", "")
            except Exception as exc:
                st.session_state["_diag_result"] = ("error", exc)

        result = st.session_state.get("_diag_result")
        if result:
            status, detail = result
            if status == "ok":
                st.success(f"Connected — fetched 1 event from `{settings.domain_list[0]}` successfully.")
            else:
                render_friendly_error(detail, key="diag_retry", context="Testing the Mailgun connection")

    st.divider()
    st.markdown("#### Logs")
    st.caption(f"Rotating file log at `{LOG_PATH}` (max 1MB × 3 backups).")
    if LOG_PATH.exists():
        st.download_button("Download log file", LOG_PATH.read_bytes(), LOG_PATH.name, "text/plain")
    else:
        st.caption("No log file yet — nothing has been logged this run.")
