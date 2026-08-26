# Mailgun Log Viewer

A small Streamlit app for querying Mailgun's [Events API](https://documentation.mailgun.com/en/latest/api-events.html)
with filters Mailgun itself doesn't support server-side (sender not-equals,
sender-domain not-contains, subject contains, ...), and picking exactly the
columns you want in the result — e.g. `@timestamp`, `message.headers.from`,
`message.headers.subject`, `message.headers.to`.

## Quick start

```
./start-unix.sh          # or start-windows.bat on Windows
```

That creates a virtual environment, installs dependencies, copies
`.env.example` to `.env` on first run, and launches the app. It starts in
**mock mode** by default — the Events page shows realistic generated sample
events with no Mailgun account required, so you can try the filters and
column picker immediately.

To go live: edit `.env` —

```
MOCK_MODE=false
MAILGUN_API_KEY=<your private API key>
MAILGUN_DOMAINS=mail.example.com
MAILGUN_REGION=us            # or eu — see below
```

and restart. See `.env.example` for every field, commented.

## Why some filters are "local" and some aren't

Mailgun's Events API accepts a real but short list of query parameters:
`event` (status), `begin`/`end`/`ascending` (date range), and `recipient`
(an *exact* address match). There is no "not equals", no "contains", and no
filter at all on the sender address or the subject — those live under
`message.headers.*` in the event JSON but Mailgun never lets you filter by
them server-side.

So this app does what Mailgun can do server-side, then finishes the job
client-side against whatever came back:

| Filter | Where it runs |
|---|---|
| Status | Mailgun (`event=`) — one call per selected status |
| Date range | Mailgun (`begin=`/`end=`) |
| To equals | Mailgun (`recipient=`, exact match) |
| From equals / not equals | Local, after fetching |
| Sender domain contains / not contains | Local, after fetching |
| Subject contains | Local, after fetching |
| To contains | Local, after fetching |

This means a very wide date range combined with only local filters can pull
(and discard) a lot of events before you see the ones you actually wanted —
narrow the date range or status first if a query feels slow. One "Fetch"
click is capped at `MAX_EVENTS_PER_QUERY` (default 3000) total events
regardless, so it can't run away.

The Events page shows this table's local-vs-Mailgun split inline, and each
event carries its full raw JSON in an expander for spot-checking.

## Log retention

Mailgun only retains events for a limited window — this account's is
**15 days** (`mailgun_log_viewer/config.py`'s `LOG_RETENTION_DAYS`). The
Events page pre-fills the date range to that window and warns if you pick
an earlier "from" date; Mailgun won't error on an out-of-range query, it'll
just silently return nothing for the part outside its retention. If your
plan's retention differs, update that constant.

## US vs EU region

Mailgun domains live in exactly one of two regions, each with its own API
base URL (`api.mailgun.net` vs `api.eu.mailgun.net`). A domain created in
one region doesn't exist in the other — querying the wrong one 401s exactly
like a bad API key would, which is a common point of confusion. Check a
domain's region on Mailgun's **Sending → Domains** page and set
`MAILGUN_REGION` to match.

## Project layout

Mirrors the shared architecture used across this author's other internal
tools (mock-first, hardened local files, friendly errors), sized down for
what this app actually needs — there's no local database, since every query
answers live from Mailgun and nothing here needs to persist across runs.

```
mailgun_log_viewer/
  config.py        Settings (pydantic-settings, .env-backed), mock_mode switch
  auth.py          HTTP Basic Auth ("api", <key>) — Mailgun has no OAuth flow
  errors.py        friendly_error() — exception -> title + plausible causes
  retry.py         call_with_retry() — retries only what friendly_error() says is transient
  logging_setup.py Rotating file logger under logs/ (Streamlit only prints to stdout)
  filters.py       EventFilters, native-vs-local query splitting, column extraction
  clients/
    base.py        Shared HTTP plumbing: request pacing, error normalization
    events.py      Mailgun Events API client (pagination via `paging.next`)
    mock.py        Realistic sample events for mock mode
  ui/
    shared.py       CSS, sidebar (domain switcher, mode badge), session state
    events_page.py  The filter form, column picker, results table, CSV export
    settings_page.py  Read-only view of the loaded .env configuration
    diagnostics_page.py  Connection test, log file download
app.py             Page router
```

## Development

```
pip install -r requirements-dev.txt
python -m pytest
python -m pyflakes mailgun_log_viewer app.py tests
```

Tests run entirely against pure logic (`filters.py`, `errors.py`, `retry.py`,
`config.py`) — no network access, no Streamlit runtime needed.

## Security notes

- No built-in authentication — this is a trusted-operator tool. Anyone who
  can run it already has whatever access `MAILGUN_API_KEY` grants.
- `.env` (holds the API key) is restricted to the owning user on POSIX
  systems at startup (`harden_file_permissions()` in `utils.py`) and is
  `.gitignore`d — don't commit it.
- CSV exports are formula-injection-safe (`safe_csv()` in `utils.py`) since
  sender/subject text originates outside this app's control.
- Every client issues `GET` requests only — this app cannot modify or
  delete anything in your Mailgun account.
