from datetime import datetime, timezone

from mailgun_log_viewer.filters import (
    EventFilters,
    _native_params,
    _passes_client_filters,
    events_to_dataframe,
    extract_row,
    fetch_mock_events,
    format_epoch,
)

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


def test_native_params_includes_status_and_dates():
    filters = EventFilters(begin=datetime(2026, 8, 1, tzinfo=timezone.utc), end=datetime(2026, 8, 20, tzinfo=timezone.utc))
    params = _native_params(filters, "delivered")
    assert params["event"] == "delivered"
    assert "begin" in params and "end" in params
    assert params["ascending"] == "no"


def test_native_params_maps_to_equals_to_recipient():
    filters = EventFilters(to_equals="jane.doe@example.com")
    params = _native_params(filters, None)
    assert params["recipient"] == "jane.doe@example.com"
    assert "event" not in params


def test_passes_client_filters_from_equals():
    filters = EventFilters(from_equals="billing@acme-mail.com")
    assert _passes_client_filters(SAMPLE_EVENT, filters) is True
    filters = EventFilters(from_equals="someone-else@acme-mail.com")
    assert _passes_client_filters(SAMPLE_EVENT, filters) is False


def test_passes_client_filters_from_not_equals():
    filters = EventFilters(from_not_equals="billing@acme-mail.com")
    assert _passes_client_filters(SAMPLE_EVENT, filters) is False
    filters = EventFilters(from_not_equals="someone-else@acme-mail.com")
    assert _passes_client_filters(SAMPLE_EVENT, filters) is True


def test_passes_client_filters_domain_not_contains():
    filters = EventFilters(domain_not_contains="acme-mail.com")
    assert _passes_client_filters(SAMPLE_EVENT, filters) is False
    filters = EventFilters(domain_not_contains="spammy-domain.com")
    assert _passes_client_filters(SAMPLE_EVENT, filters) is True


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
    events = fetch_mock_events("mock.example.com", filters, seed=42)
    assert events  # deterministic seed should produce at least one failed event
    assert all(e["event"] == "failed" for e in events)


def test_fetch_mock_events_from_not_equals_excludes_matches():
    baseline = fetch_mock_events("mock.example.com", EventFilters(), seed=42)
    sender_to_exclude = baseline[0]["envelope"]["sender"]
    filtered = fetch_mock_events("mock.example.com", EventFilters(from_not_equals=sender_to_exclude), seed=42)
    assert all(e["envelope"]["sender"] != sender_to_exclude for e in filtered)
