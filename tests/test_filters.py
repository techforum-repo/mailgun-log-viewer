from datetime import datetime, timezone
from email.utils import format_datetime

from mailgun_log_viewer.filters import (
    EventFilters,
    ResultFilter,
    _native_params,
    _passes_client_filters,
    apply_result_filters,
    events_to_dataframe,
    extract_row,
    fetch_mock_events,
    format_epoch,
)
from mailgun_log_viewer.utils import get_path

SAMPLE_EVENT = {
    "id": "abc123",
    "timestamp": 1700000000.0,
    "event": "delivered",
    "recipient": "jane.doe@example.com",
    "message": {
        "headers": {
            "from": "Acme Billing <billing@acme-mail.com>",
            "to": "jane.doe@example.com",
            "subject": "Your invoice is ready",
        },
    },
    "tags": ["billing", "transactional"],
}


def test_native_params_swaps_begin_end_for_descending_default():
    """Regression: Mailgun's begin/end are directional, not "start/end of
    range" — with ascending=no (the default, "newest first"), Mailgun walks
    backward from a newer begin to an older end, so the user's older/newer
    picks must be swapped or Mailgun 400s with "Inconsistent range" (as it
    did, live, before this swap existed)."""
    older = datetime(2026, 8, 11, tzinfo=timezone.utc)
    newer = datetime(2026, 8, 26, tzinfo=timezone.utc)
    filters = EventFilters(begin=older, end=newer, ascending=False)
    params = _native_params(filters, "delivered")
    assert params["event"] == "delivered"
    assert params["ascending"] == "no"
    assert params["begin"] == format_datetime(newer)
    assert params["end"] == format_datetime(older)


def test_native_params_keeps_begin_end_as_picked_for_ascending():
    older = datetime(2026, 8, 11, tzinfo=timezone.utc)
    newer = datetime(2026, 8, 26, tzinfo=timezone.utc)
    filters = EventFilters(begin=older, end=newer, ascending=True)
    params = _native_params(filters, None)
    assert params["ascending"] == "yes"
    assert params["begin"] == format_datetime(older)
    assert params["end"] == format_datetime(newer)


def test_native_params_maps_to_equals_to_recipient():
    params = _native_params(EventFilters(), None, recipient="jane.doe@example.com")
    assert params["recipient"] == "jane.doe@example.com"
    assert "event" not in params


def test_passes_client_filters_from_equals():
    filters = EventFilters(from_equals=["billing@acme-mail.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is True
    filters = EventFilters(from_equals=["someone-else@acme-mail.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is False


def test_passes_client_filters_from_equals_multiple_is_or():
    """Multiple From-equals addresses match if the sender is *any* of them."""
    filters = EventFilters(from_equals=["someone-else@acme-mail.com", "billing@acme-mail.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is True
    filters = EventFilters(from_equals=["someone-else@acme-mail.com", "another@acme-mail.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is False


def test_passes_client_filters_from_not_equals():
    filters = EventFilters(from_not_equals=["billing@acme-mail.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is False
    filters = EventFilters(from_not_equals=["someone-else@acme-mail.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is True


def test_passes_client_filters_from_not_equals_multiple_excludes_any_match():
    filters = EventFilters(from_not_equals=["someone-else@acme-mail.com", "billing@acme-mail.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is False


def test_passes_client_filters_from_contains_matches_display_name_too():
    """Unlike from_equals/from_not_equals (bare address), from_contains
    matches the raw header text — so it also catches display-name text,
    e.g. "Acme" here, not just an address fragment."""
    filters = EventFilters(from_contains=["Acme"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is True
    filters = EventFilters(from_contains=["billing"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is True
    filters = EventFilters(from_contains=["nomatch"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is False


def test_passes_client_filters_from_not_contains():
    filters = EventFilters(from_not_contains=["acme-mail.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is False
    filters = EventFilters(from_not_contains=["spammy-domain.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is True


def test_passes_client_filters_domain_not_contains():
    filters = EventFilters(domain_not_contains=["acme-mail.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is False
    filters = EventFilters(domain_not_contains=["spammy-domain.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is True


def test_passes_client_filters_domain_contains_multiple_is_or():
    filters = EventFilters(domain_contains=["spammy-domain.com", "acme-mail.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is True
    filters = EventFilters(domain_contains=["spammy-domain.com", "other-domain.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is False


def test_passes_client_filters_to_not_equals_matches_against_recipient_field():
    """Unlike to_contains (checked against the raw to_header), to_not_equals
    is checked against Mailgun's own `recipient` field to mirror to_equals's
    exact-match semantics."""
    filters = EventFilters(to_not_equals=["jane.doe@example.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is False
    filters = EventFilters(to_not_equals=["someone-else@example.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is True


def test_passes_client_filters_to_not_contains():
    filters = EventFilters(to_not_contains=["example.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is False
    filters = EventFilters(to_not_contains=["other-domain.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is True


def test_passes_client_filters_to_not_equals_multiple_excludes_any_match():
    filters = EventFilters(to_not_equals=["someone-else@example.com", "jane.doe@example.com"])
    assert _passes_client_filters(SAMPLE_EVENT, filters) is False


def test_passes_client_filters_subject_contains_case_insensitive():
    filters = EventFilters(subject_contains="INVOICE")
    assert _passes_client_filters(SAMPLE_EVENT, filters) is True
    filters = EventFilters(subject_contains="refund")
    assert _passes_client_filters(SAMPLE_EVENT, filters) is False


def test_format_epoch_valid_and_invalid():
    assert format_epoch(1700000000.0).startswith("2023-11-14")
    assert format_epoch(None) == ""
    assert format_epoch("not-a-number") == ""


def test_extract_row_timestamp_and_list_join():
    row = extract_row(SAMPLE_EVENT, ["@timestamp", "message.headers.subject", "tags"])
    assert row["@timestamp"].startswith("2023-11-14")
    assert row["message.headers.subject"] == "Your invoice is ready"
    assert row["tags"] == "billing, transactional"


def test_events_to_dataframe_uses_requested_columns():
    df = events_to_dataframe([SAMPLE_EVENT], ["message.headers.from", "message.headers.to"])
    assert list(df.columns) == ["message.headers.from", "message.headers.to"]
    assert df.iloc[0]["message.headers.to"] == "jane.doe@example.com"


def test_fetch_mock_events_respects_status_filter():
    filters = EventFilters(statuses=["failed"])
    events = fetch_mock_events(["mock.example.com"], filters, seed=42)
    assert events  # deterministic seed should produce at least one failed event
    assert all(e["event"] == "failed" for e in events)


def test_fetch_mock_events_from_not_equals_excludes_matches():
    baseline = fetch_mock_events(["mock.example.com"], EventFilters(), seed=42)
    sender_to_exclude = baseline[0]["envelope"]["sender"]
    filtered = fetch_mock_events(["mock.example.com"], EventFilters(from_not_equals=[sender_to_exclude]), seed=42)
    assert all(e["envelope"]["sender"] != sender_to_exclude for e in filtered)


def test_fetch_mock_events_to_equals_multiple_addresses_is_or():
    baseline = fetch_mock_events(["mock.example.com"], EventFilters(), seed=42)
    recipients = sorted({e["recipient"] for e in baseline})
    assert len(recipients) >= 2
    wanted = recipients[:2]
    filtered = fetch_mock_events(["mock.example.com"], EventFilters(to_equals=wanted), seed=42)
    assert filtered
    assert all(e["recipient"] in wanted for e in filtered)


_OTHER_EVENT = {**SAMPLE_EVENT, "timestamp": 1700010000.0, "message": {"headers": {"from": "Other <other@spammy.com>", "to": "x@y.com", "subject": "Refund"}}}


def test_apply_result_filters_text_field_matches_case_insensitive():
    df = events_to_dataframe([SAMPLE_EVENT, _OTHER_EVENT], ["message.headers.from", "message.headers.subject"])
    result = apply_result_filters(df, [ResultFilter(field="message.headers.subject", text="INVOICE")])
    assert len(result) == 1
    assert result.iloc[0]["message.headers.subject"] == "Your invoice is ready"


def test_apply_result_filters_multiple_rows_combine_with_and():
    df = events_to_dataframe([SAMPLE_EVENT, _OTHER_EVENT], ["message.headers.from", "message.headers.subject"])
    result = apply_result_filters(
        df,
        [ResultFilter(field="message.headers.from", text="acme-mail.com"), ResultFilter(field="message.headers.subject", text="refund")],
    )
    assert result.empty  # no row matches both conditions


def test_apply_result_filters_empty_text_is_a_noop():
    df = events_to_dataframe([SAMPLE_EVENT], ["message.headers.subject"])
    result = apply_result_filters(df, [ResultFilter(field="message.headers.subject", text="  ")])
    assert len(result) == len(df)


def test_apply_result_filters_unknown_field_is_a_noop():
    df = events_to_dataframe([SAMPLE_EVENT], ["message.headers.subject"])
    result = apply_result_filters(df, [ResultFilter(field="message.headers.to", text="anything")])
    assert len(result) == len(df)


def test_apply_result_filters_timestamp_bounds():
    df = events_to_dataframe([SAMPLE_EVENT, _OTHER_EVENT], ["@timestamp"])
    begin = datetime.fromtimestamp(1700005000.0, tz=timezone.utc)
    result = apply_result_filters(df, [ResultFilter(field="@timestamp", begin=begin)])
    assert len(result) == 1
    assert result.iloc[0]["@timestamp"] == format_epoch(1700010000.0)


def test_apply_result_filters_timestamp_no_bounds_is_a_noop():
    df = events_to_dataframe([SAMPLE_EVENT], ["@timestamp"])
    result = apply_result_filters(df, [ResultFilter(field="@timestamp")])
    assert len(result) == len(df)


def test_apply_result_filters_preserves_original_index():
    """Regression: the Events page uses the surviving index to look up the
    matching raw event (events[visible_table.index[0]]) — apply_result_filters
    must mask rows, not reset the index, or that lookup would point at the
    wrong event."""
    df = events_to_dataframe([SAMPLE_EVENT, SAMPLE_EVENT, SAMPLE_EVENT], ["message.headers.subject"])
    result = apply_result_filters(df, [ResultFilter(field="message.headers.subject", text="invoice")])
    assert list(result.index) == [0, 1, 2]


def test_fetch_mock_events_queries_every_configured_domain():
    """Regression: a single-domain picker used to make this filter
    redundant with it — now every configured domain is always queried and
    merged, so results can come from more than one."""
    events = fetch_mock_events(["brand-a.example.com", "brand-b.example.com"], EventFilters(), seed=42)
    message_ids = [str(get_path(e, "message.headers.message-id")) for e in events]
    assert any("brand-a.example.com" in mid for mid in message_ids)
    assert any("brand-b.example.com" in mid for mid in message_ids)
