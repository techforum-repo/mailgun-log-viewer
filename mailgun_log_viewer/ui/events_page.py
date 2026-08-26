from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import streamlit as st

from .. import filters as filters_module
from ..config import LOG_RETENTION_DAYS
from ..filters import COLUMN_OPTIONS, DEFAULT_COLUMNS, EVENT_TYPES, EventFilters
from ..utils import run_async, safe_csv
from .shared import fetch_button, get_active_domain, render_friendly_error


def _default_begin() -> datetime:
    # Pre-filled to the account's actual retention window (see
    # config.LOG_RETENTION_DAYS) rather than an arbitrary "last 7 days" —
    # picking an earlier date wouldn't error, it would just silently return
    # nothing beyond what Mailgun still has.
    return datetime.now(timezone.utc) - timedelta(days=LOG_RETENTION_DAYS)


def _build_filters() -> EventFilters:
    st.markdown("#### Filters")

    col1, col2 = st.columns(2)
    with col1:
        st.caption("Sender")
        from_equals = st.text_input("From equals", key="f_from_equals", placeholder="alerts@example.com")
        from_not_equals = st.text_input("From not equals", key="f_from_not_equals", placeholder="noreply@spammy-domain.com")
        domain_contains = st.text_input("Sender domain contains", key="f_domain_contains", placeholder="example.com")
        domain_not_contains = st.text_input("Sender domain not contains", key="f_domain_not_contains", placeholder="mailgun.org")
    with col2:
        st.caption("Recipient & subject")
        to_equals = st.text_input("To equals (exact address)", key="f_to_equals", placeholder="jane.doe@example.com")
        to_contains = st.text_input("To contains", key="f_to_contains", placeholder="@example.com")
        subject_contains = st.text_input("Subject contains", key="f_subject_contains", placeholder="invoice")

    st.caption("Status & date range")
    col3, col4, col5 = st.columns([2, 1, 1])
    with col3:
        statuses = st.multiselect("Status", EVENT_TYPES, default=["delivered"], key="f_statuses")
    with col4:
        begin_date = st.date_input("From date (UTC)", value=_default_begin().date(), key="f_begin_date")
    with col5:
        end_date = st.date_input("To date (UTC)", value=datetime.now(timezone.utc).date(), key="f_end_date")
    ascending = st.checkbox("Oldest first", key="f_ascending", value=False)

    begin_dt = datetime.combine(begin_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
    if begin_dt < _default_begin() - timedelta(days=1):
        st.caption(f"⚠️ Mailgun retains roughly the last {LOG_RETENTION_DAYS} days of events — results before then will be empty regardless of this filter.")

    return EventFilters(
        statuses=statuses,
        begin=begin_dt,
        end=end_dt,
        ascending=ascending,
        from_equals=from_equals,
        from_not_equals=from_not_equals,
        domain_contains=domain_contains,
        domain_not_contains=domain_not_contains,
        subject_contains=subject_contains,
        to_equals=to_equals,
        to_contains=to_contains,
    )


def _do_fetch(domain: str, spec: EventFilters) -> None:
    try:
        events = run_async(filters_module.fetch_events(domain, spec, mock_seed=st.session_state.mock_seed))
        st.session_state.events_rows = events
        st.session_state["_events_error"] = None
    except Exception as exc:
        st.session_state["_events_error"] = exc


def render() -> None:
    st.markdown("### Events")
    st.caption(
        f"Domain: **{get_active_domain() or '(none configured)'}**. Mailgun's Events API has no native "
        "\"not equals\"/\"not contains\"/sender/subject filters — Status and dates are sent to Mailgun; "
        "everything else is applied to the results locally after fetching."
    )

    spec = _build_filters()

    default_columns = st.session_state.get("events_columns") or DEFAULT_COLUMNS
    columns = st.multiselect(
        "Columns",
        list(COLUMN_OPTIONS.keys()),
        default=default_columns,
        key="events_columns",
        format_func=lambda c: f"{c} — {COLUMN_OPTIONS[c]}",
    )

    if fetch_button("Fetch events", key="events_fetch"):
        _do_fetch(get_active_domain(), spec)

    error = st.session_state.get("_events_error")
    if error is not None:
        if render_friendly_error(error, key="events_retry", context="Fetching events"):
            _do_fetch(get_active_domain(), spec)
            st.rerun()
        return

    events = st.session_state.events_rows
    if events is None:
        st.info("Set your filters above and click **Fetch events**.")
        return

    st.caption(f"{len(events)} event(s) matched.")
    if not events:
        st.info("No events matched these filters in the queried window.")
        return

    table = filters_module.events_to_dataframe(events, columns or DEFAULT_COLUMNS)
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.download_button("Download as CSV", safe_csv(table), "mailgun_events.csv", "text/csv")

    with st.expander("Raw event (first result)"):
        st.json(events[0], expanded=False)
