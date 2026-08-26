from mailgun_log_viewer.errors import friendly_error


def test_connection_failure_is_classified_and_retryable():
    info = friendly_error(RuntimeError("Cannot connect to Mailgun. Check network/proxy/firewall. Endpoint: https://x"))
    assert info.title == "Mailgun connection failed"
    assert info.reasons
    assert info.retryable is True


def test_missing_configuration_is_not_retryable():
    info = friendly_error(RuntimeError("Mailgun is not configured — MAILGUN_API_KEY is missing from .env."))
    assert info.title == "Mailgun is not configured"
    assert info.retryable is False


def test_unauthorized_is_not_retryable_and_mentions_region():
    info = friendly_error(RuntimeError("Mailgun returned HTTP 401: unauthorized"))
    assert "unauthorized" in info.title.lower()
    assert info.retryable is False
    assert any("region" in reason.lower() for reason in info.reasons)


def test_not_found_is_not_retryable():
    info = friendly_error(RuntimeError("Mailgun returned HTTP 404: not found"))
    assert info.title == "Domain not found"
    assert info.retryable is False


def test_rate_limit_is_retryable():
    info = friendly_error(RuntimeError("Mailgun returned HTTP 429: too many requests"))
    assert "rate-limiting" in info.title.lower()
    assert info.retryable is True


def test_timeout_is_retryable():
    info = friendly_error(RuntimeError("Mailgun request timed out. Endpoint: https://x"))
    assert info.title == "Mailgun request timed out"
    assert info.retryable is True


def test_server_error_is_retryable():
    info = friendly_error(RuntimeError("Mailgun returned HTTP 500: internal error"))
    assert info.title == "Mailgun returned a server error"
    assert info.retryable is True


def test_unknown_error_falls_back_to_generic_message():
    info = friendly_error(ValueError("something obscure happened"))
    assert info.title == "Something went wrong"
    assert info.reasons == ["something obscure happened"]
