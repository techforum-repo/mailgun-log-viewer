from datetime import datetime, timezone

from mailgun_log_viewer.utils import extract_domain, extract_email_address, get_path, local_now, parse_list, sanitize_csv_cell, to_utc


def test_extract_email_address_with_display_name():
    assert extract_email_address("Jane Doe <jane@example.com>") == "jane@example.com"


def test_extract_email_address_bare():
    assert extract_email_address("jane@example.com") == "jane@example.com"


def test_extract_email_address_empty():
    assert extract_email_address("") == ""
    assert extract_email_address(None) == ""


def test_extract_domain():
    assert extract_domain("Jane Doe <jane@example.com>") == "example.com"
    assert extract_domain("no-at-sign") == ""


def test_get_path_nested():
    event = {"message": {"headers": {"subject": "Hi"}}}
    assert get_path(event, "message.headers.subject") == "Hi"


def test_get_path_missing_segment_returns_empty_string():
    event = {"message": {}}
    assert get_path(event, "message.headers.subject") == ""


def test_get_path_non_dict_intermediate():
    event = {"message": "not-a-dict"}
    assert get_path(event, "message.headers.subject") == ""


def test_sanitize_csv_cell_neutralizes_formula_prefix():
    assert sanitize_csv_cell("=cmd|'/c calc'!A1") == "'=cmd|'/c calc'!A1"


def test_sanitize_csv_cell_leaves_normal_text():
    assert sanitize_csv_cell("Weekly digest") == "Weekly digest"


def test_to_utc_handles_daylight_saving_offset():
    """Aug 26 is inside US Central daylight saving (CDT, UTC-5) — midnight
    Central should land on 05:00 UTC, not 06:00."""
    midnight_central = datetime(2026, 8, 26, 0, 0, 0)
    assert to_utc(midnight_central, "America/Chicago") == datetime(2026, 8, 26, 5, 0, 0, tzinfo=timezone.utc)


def test_to_utc_handles_standard_time_offset():
    """Jan 15 is outside daylight saving (CST, UTC-6) — this is the whole
    point of using zoneinfo instead of a fixed offset: the same "midnight
    Central" wall-clock time converts differently depending on the date."""
    midnight_central = datetime(2026, 1, 15, 0, 0, 0)
    assert to_utc(midnight_central, "America/Chicago") == datetime(2026, 1, 15, 6, 0, 0, tzinfo=timezone.utc)


def test_to_utc_falls_back_to_utc_for_unknown_zone():
    naive = datetime(2026, 8, 26, 12, 0, 0)
    assert to_utc(naive, "Not/A_Real_Zone") == naive.replace(tzinfo=timezone.utc)


def test_local_now_falls_back_to_utc_for_unknown_zone():
    result = local_now("Not/A_Real_Zone")
    assert result.tzinfo == timezone.utc


def test_local_now_returns_aware_datetime_for_valid_zone():
    result = local_now("America/Chicago")
    assert result.tzinfo is not None
    assert result.utcoffset() is not None


def test_parse_list_splits_and_trims():
    assert parse_list("alerts@example.com, billing@example.com") == ["alerts@example.com", "billing@example.com"]


def test_parse_list_drops_empty_entries():
    assert parse_list("alerts@example.com, , billing@example.com,") == ["alerts@example.com", "billing@example.com"]


def test_parse_list_empty_string_returns_empty_list():
    assert parse_list("") == []
    assert parse_list("   ") == []


def test_parse_list_single_value_no_comma():
    assert parse_list("alerts@example.com") == ["alerts@example.com"]
