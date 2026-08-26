from mailgun_log_viewer.utils import extract_domain, extract_email_address, get_path, sanitize_csv_cell


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
