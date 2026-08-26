from mailgun_log_viewer.errors import MailgunRateLimitError
from mailgun_log_viewer.retry import MAX_RETRY_AFTER_SECONDS, call_with_retry


def test_succeeds_on_first_try_without_sleeping():
    sleeps = []
    result = call_with_retry(lambda: 42, sleep=sleeps.append)
    assert result.success is True
    assert result.value == 42
    assert result.attempts == 1
    assert result.retries == 0
    assert sleeps == []


def test_retries_transient_failure_then_succeeds():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("Mailgun request timed out. Endpoint: https://x")
        return "ok"

    sleeps = []
    result = call_with_retry(flaky, sleep=sleeps.append)
    assert result.success is True
    assert result.value == "ok"
    assert result.attempts == 3
    assert result.retries == 2
    assert len(sleeps) == 2
    assert sleeps == sorted(sleeps)  # exponential: each delay >= the previous


def test_stops_immediately_on_permanent_failure():
    calls = {"n": 0}

    def always_unauthorized():
        calls["n"] += 1
        raise RuntimeError("Mailgun returned HTTP 401: unauthorized")

    sleeps = []
    result = call_with_retry(always_unauthorized, sleep=sleeps.append)
    assert result.success is False
    assert calls["n"] == 1  # no retry attempted
    assert result.retries == 0
    assert sleeps == []


def test_gives_up_after_max_attempts_on_persistent_transient_failure():
    calls = {"n": 0}

    def always_times_out():
        calls["n"] += 1
        raise RuntimeError("Mailgun request timed out. Endpoint: https://x")

    sleeps = []
    result = call_with_retry(always_times_out, max_attempts=3, sleep=sleeps.append)
    assert result.success is False
    assert calls["n"] == 3
    assert result.retries == 2
    assert len(sleeps) == 2


def test_honors_mailguns_retry_after_hint_instead_of_exponential_backoff():
    calls = {"n": 0}

    def rate_limited_then_ok():
        calls["n"] += 1
        if calls["n"] < 2:
            raise MailgunRateLimitError("Mailgun returned HTTP 429: too many requests", retry_after=3.5)
        return "ok"

    sleeps = []
    result = call_with_retry(rate_limited_then_ok, sleep=sleeps.append)
    assert result.success is True
    assert sleeps == [3.5]  # not the exponential default (1.0)


def test_caps_an_unreasonably_large_retry_after():
    def always_rate_limited():
        raise MailgunRateLimitError("Mailgun returned HTTP 429: too many requests", retry_after=9999.0)

    sleeps = []
    call_with_retry(always_rate_limited, max_attempts=2, sleep=sleeps.append)
    assert sleeps == [MAX_RETRY_AFTER_SECONDS]
