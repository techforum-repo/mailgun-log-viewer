from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import streamlit as st

from .. import filters as filters_module
from ..config import LOG_RETENTION_DAYS, settings
from ..filters import COLUMN_OPTIONS, DEFAULT_COLUMNS, EVENT_TYPES, EventFilters
from ..utils import local_now, parse_list, run_async, safe_csv, to_utc
from .shared import fetch_button, query_domains, render_friendly_error

# A curated shortlist for the timezone picker, not an exhaustive IANA list —
# settings.report_timezone (whatever .env sets, default "America/Chicago")
# is always included even if it's not one of these, so a custom zone in
# .env still shows up as the pre-selected option.
_COMMON_TIMEZONES = ["America/Chicago", "UTC", "America/New_York", "America/Denver", "America/Los_Angeles", "Europe/London"]


def _timezone_options() -> list[str]:
    options = list(_COMMON_TIMEZONES)
    if settings.report_timezone not in options:
        options.insert(0, settings.report_timezone)
    return options


def _build_filters() -> EventFilters:
    st.markdown("#### Filters")

    # From, Sender domain, and To each get their own operator dropdown next
    # to a value field — Subject deliberately does NOT (it's placed in its
    # own row below, outside both columns) since it only ever supports
    # "contains"; keeping it out of the Sender/Recipient columns avoids it
    # looking like it shares an operator with either.
    _ADDRESS_OPERATORS = ["equals", "not equals", "contains", "not contains"]

    col1, col2 = st.columns(2)
    with col1:
        st.caption("Sender")
        from_op_col, from_value_col = st.columns([1, 2])
        with from_op_col:
            from_operator = st.selectbox("Operator", _ADDRESS_OPERATORS, key="f_from_operator")
        with from_value_col:
            from_value = st.text_input(
                "From", key="f_from_value", placeholder="alerts@example.com, billing@example.com",
                help="Comma-separated for multiple — matches any one of them (OR).",
            )
        domain_op_col, domain_value_col = st.columns([1, 2])
        with domain_op_col:
            domain_operator = st.selectbox("Operator", ["contains", "not contains"], key="f_domain_operator")
        with domain_value_col:
            domain_value = st.text_input(
                "Sender domain", key="f_domain_value", placeholder="example.com, mailgun.org",
                help="Comma-separated for multiple — matches any one of them (OR).",
            )
    with col2:
        st.caption("Recipient")
        to_op_col, to_value_col = st.columns([1, 2])
        with to_op_col:
            to_operator = st.selectbox("Operator", _ADDRESS_OPERATORS, key="f_to_operator")
        with to_value_col:
            to_value = st.text_input(
                "To", key="f_to_value", placeholder="jane.doe@example.com, john.smith@example.org",
                help="Comma-separated for multiple — matches any one of them (OR).",
            )

    st.caption("Subject")
    subject_contains = st.text_input(
        "Subject contains", key="f_subject_contains", placeholder="invoice",
        help="Always a substring match — Subject has no equals/not-equals/not-contains operator, unlike From/To above.",
    )

    from_list = parse_list(from_value)
    domain_list = parse_list(domain_value)
    to_list = parse_list(to_value)

    from_equals = from_list if from_operator == "equals" else []
    from_not_equals = from_list if from_operator == "not equals" else []
    from_contains = from_list if from_operator == "contains" else []
    from_not_contains = from_list if from_operator == "not contains" else []
    domain_contains = domain_list if domain_operator == "contains" else []
    domain_not_contains = domain_list if domain_operator == "not contains" else []
    # "equals" maps to Mailgun's native `recipient` param (see filters.py) —
    # only true when the value is used that way, so switching to another
    # operator doesn't silently keep sending it server-side. Multiple
    # "equals" addresses become one native call per address; the other
    # three operators have no native equivalent and are always local.
    to_equals = to_list if to_operator == "equals" else []
    to_not_equals = to_list if to_operator == "not equals" else []
    to_contains = to_list if to_operator == "contains" else []
    to_not_contains = to_list if to_operator == "not contains" else []

    st.caption("Status & date range")
    tz_options = _timezone_options()
    col3, col4, col5, col6 = st.columns([2, 1, 1, 1.2])
    with col3:
        statuses = st.multiselect("Status", EVENT_TYPES, default=["delivered"], key="f_statuses")
    with col6:
        tz_name = st.selectbox("Timezone", tz_options, index=tz_options.index(settings.report_timezone), key="f_timezone")
    with col4:
        begin_date = st.date_input(
            "From date", value=(local_now(tz_name) - timedelta(days=LOG_RETENTION_DAYS)).date(), key="f_begin_date"
        )
    with col5:
        end_date = st.date_input("To date", value=local_now(tz_name).date(), key="f_end_date")
    ascending = st.checkbox("Oldest first", key="f_ascending", value=False)

    # Both dates picked above are calendar days in `tz_name`, not UTC —
    # Central midnight (say) is 05:00 or 06:00 UTC depending on whether
    # CDT or CST is in effect, so this can't just tack on tzinfo=UTC. See
    # utils.to_utc's docstring for why zoneinfo (not a fixed offset)
    # handles that DST switch correctly.
    begin_dt = to_utc(datetime.combine(begin_date, time.min), tz_name)
    end_dt = to_utc(datetime.combine(end_date, time.max), tz_name)
    st.caption(f"Querying UTC window: {begin_dt.strftime('%Y-%m-%d %H:%M')} → {end_dt.strftime('%Y-%m-%d %H:%M')} UTC")
    if begin_dt < datetime.now(timezone.utc) - timedelta(days=LOG_RETENTION_DAYS + 1):
        st.caption(f"⚠️ Mailgun retains roughly the last {LOG_RETENTION_DAYS} days of events — results before then will be empty regardless of this filter.")

    spec = EventFilters(
        statuses=statuses,
        begin=begin_dt,
        end=end_dt,
        ascending=ascending,
        from_equals=from_equals,
        from_not_equals=from_not_equals,
        from_contains=from_contains,
        from_not_contains=from_not_contains,
        domain_contains=domain_contains,
        domain_not_contains=domain_not_contains,
        subject_contains=subject_contains,
        to_equals=to_equals,
        to_not_equals=to_not_equals,
        to_contains=to_contains,
        to_not_contains=to_not_contains,
    )
    return spec


def _do_fetch(domains: list[str], spec: EventFilters) -> None:
    try:
        events = run_async(filters_module.fetch_events(domains, spec, mock_seed=st.session_state.mock_seed))
        st.session_state.events_rows = events
        st.session_state["_events_error"] = None
    except Exception as exc:
        st.session_state["_events_error"] = exc


def render() -> None:
    st.markdown("### Events")
    domains = query_domains()
    st.caption(
        f"Domain(s): **{', '.join(domains) or '(none configured)'}**. Mailgun's Events API has no native "
        "\"not equals\"/\"not contains\"/sender/subject filters — Status and dates are sent to Mailgun; "
        "everything else is applied to the results locally after fetching."
    )

    spec = _build_filters()

    columns = st.multiselect(
        "Columns",
        list(COLUMN_OPTIONS.keys()),
        default=DEFAULT_COLUMNS,
        key="events_columns",
        format_func=lambda c: f"{c} — {COLUMN_OPTIONS[c]}",
    )

    if fetch_button("Fetch events", key="events_fetch"):
        _do_fetch(domains, spec)

    error = st.session_state.get("_events_error")
    if error is not None:
        if render_friendly_error(error, key="events_retry", context="Fetching events"):
            _do_fetch(domains, spec)
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

    search = st.text_input(
        "Search results", key="results_search", placeholder="Type to narrow the table below by any visible text...",
        help="Filters the already-fetched rows shown below — no new Mailgun call. Matches any of the selected columns, case-insensitive.",
    )
    visible_table = filters_module.filter_table(table, search)
    if search.strip():
        st.caption(f"{len(visible_table)} of {len(table)} row(s) match \"{search.strip()}\".")

    st.dataframe(visible_table, use_container_width=True, hide_index=True)
    st.download_button("Download as CSV", safe_csv(visible_table), "mailgun_events.csv", "text/csv")

    with st.expander("Raw event (first visible result)"):
        if visible_table.empty:
            st.caption("No visible rows to show.")
        else:
            # filter_table() only masks rows — it never resets the index —
            # so the DataFrame's own index still lines up with `events`'
            # original position, letting this show the same row the table
            # and search caption above are currently displaying, not always
            # the pre-search events[0].
            st.json(events[visible_table.index[0]], expanded=False)
