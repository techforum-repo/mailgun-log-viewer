from mailgun_log_viewer.config import Settings


def test_domain_list_splits_and_trims():
    settings = Settings(mailgun_domains=" mail.example.com, updates.example.com ,")
    assert settings.domain_list == ["mail.example.com", "updates.example.com"]


def test_domain_list_empty_when_unset():
    assert Settings(mailgun_domains="").domain_list == []


def test_mailgun_configured_requires_key_and_domain():
    assert Settings(mailgun_api_key="", mailgun_domains="mail.example.com").mailgun_configured is False
    assert Settings(mailgun_api_key="key-123", mailgun_domains="").mailgun_configured is False
    assert Settings(mailgun_api_key="key-123", mailgun_domains="mail.example.com").mailgun_configured is True


def test_base_url_by_region():
    assert Settings(mailgun_region="us").mailgun_base_url == "https://api.mailgun.net/v3"
    assert Settings(mailgun_region="eu").mailgun_base_url == "https://api.eu.mailgun.net/v3"


def test_base_url_defaults_to_us_for_unknown_region():
    assert Settings(mailgun_region="mars").mailgun_base_url == "https://api.mailgun.net/v3"


def test_base_url_region_is_case_insensitive():
    assert Settings(mailgun_region="EU").mailgun_base_url == "https://api.eu.mailgun.net/v3"


def test_report_timezone_defaults_to_central():
    assert Settings().report_timezone == "America/Chicago"
