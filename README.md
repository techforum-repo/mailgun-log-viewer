# Mailgun Log Viewer

A small Streamlit app for querying Mailgun's [Events API](https://documentation.mailgun.com/en/latest/api-events.html)
across every domain on your account at once, with filters Mailgun itself
doesn't support server-side (sender not-equals, sender-domain not-contains,
subject contains, multi-value OR matches, ...), timezone-aware date ranges,
and picking exactly the columns you want in the result — e.g. `@timestamp`,
`message.headers.from`, `message.headers.subject`, `message.headers.to`.

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
REPORT_TIMEZONE=America/Chicago  # default for the Events page's date-range timezone — see below
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
| To — equals | Mailgun (`recipient=`, exact match) |
| From — equals / not equals | Local, after fetching |
| Sender domain — contains / not contains | Local, after fetching |
| Subject contains | Local, after fetching |
| To — contains | Local, after fetching |

From, Sender domain, and To are each a single value field plus an operator
dropdown next to it — one field, not a pair of boxes for "equals" and "not
equals". Only the operator actually chosen determines which underlying
filter fires; e.g. switching To's operator from "equals" to "contains"
stops sending `recipient=` server-side and starts filtering locally instead.

Each of those three fields also accepts **more than one value** —
comma-separate them (`alerts@example.com, billing@example.com`) and they're
OR'd together: "From equals" matches if the sender is *any* of them, "To
equals" fires one native `recipient=` call per address and merges the
results (Mailgun's API takes exactly one recipient per call), and "Sender
domain contains" matches if the domain contains *any* of the listed values.
The same OR logic applies to the "not equals"/"not contains" side —
excluded if it matches *any* of them.

This means a very wide date range combined with only local filters can pull
(and discard) a lot of events before you see the ones you actually wanted —
narrow the date range or status first if a query feels slow. One "Fetch"
click is capped at `MAX_EVENTS_PER_QUERY` (default 3000) total events
regardless, so it can't run away.

The Events page shows this table's local-vs-Mailgun split inline, and each
event carries its full raw JSON in an expander for spot-checking.

### Begin/end are directional, not "start of range / end of range"

Mailgun's `begin`/`end` don't mean "earlier bound / later bound" — they mean
"where the cursor starts / where it stops," and which one has to be the
later timestamp depends on `ascending`. With "Oldest first" unchecked
(descending, Mailgun's default), it walks *backward* from a newer `begin`
to an older `end`; checked, it walks forward from an older `begin` to a
newer `end`. Typing an ordinary "from the 11th to the 26th" and sending it
unswapped against the descending default gets rejected by Mailgun as
`Inconsistent range`. `filters.py`'s `_native_params()` swaps them for you
based on `ascending` so the UI's "From date"/"To date" can stay in the
plain older→newer order no matter which direction you're sorting.

## Date filters are timezone-aware, not just UTC

The Events page's date range includes a **Timezone** picker (defaults to
`REPORT_TIMEZONE` in `.env`, "America/Chicago" out of the box). "From date"
and "To date" are calendar days in *that* zone, not UTC — picking the same
date for both gives you exactly that one 24-hour day. Behind the scenes this
uses Python's stdlib `zoneinfo` (`utils.to_utc()`/`utils.local_now()`, no
extra dependency) to convert to the correct UTC window before querying
Mailgun or filtering mock data, which correctly handles the twice-a-year
DST switch — Central midnight is `05:00 UTC` under CDT but `06:00 UTC` under
CST, and a fixed offset would get half the year wrong. The page always shows
the computed UTC window in a caption so you can verify exactly what's being
sent.

This is independent of two other timezone-shaped settings that are easy to
conflate with it: `MAILGUN_REGION` (which Mailgun *API* to call, US vs EU —
see below) and whatever display-timezone your Mailgun account's own
dashboard is set to (that's cosmetic to Mailgun's web UI only; this app
never reads it, so a report built here can show a given event at a
different clock time than Mailgun's own dashboard does if your account's
dashboard timezone differs from `REPORT_TIMEZONE`).

## Chart: volume by sender, hourly

Below the results table, a stacked bar chart shows event count per hour
bucket, broken down by sender address — built with Streamlit's native
charting (no extra dependency), so it comes with a built-in "⋮" menu
(hover the chart, top-right) to download it as a PNG for pasting into a
report. Hour buckets are computed in whichever timezone the date-range
picker above is set to (`filters.sender_hourly_counts()` /
`utils.local_hour_bucket()`), not UTC, so they line up with the rest of the
page. Only the 8 busiest senders in the current result set get their own
color; everyone else is folded into "Other" so a domain with dozens of
senders doesn't turn the chart into noise.

## Every configured domain is queried together

There's no per-session "which domain" picker — every domain listed in
`MAILGUN_DOMAINS` is queried and merged on every "Fetch" click. This used to
be a single-domain sidebar selector, which made the Sender domain filter
above redundant with it (it could never narrow anything the sidebar hadn't
already fixed). If your account only has one domain, this changes nothing
for you day-to-day; if it has several — e.g. one Mailgun domain sending on
behalf of multiple sub-brand `From` addresses, or several verified domains
in one account — Sender domain now does real work across all of them at
once instead of one at a time.

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
  filters.py       EventFilters (multi-value OR filters), native-vs-local query splitting, column extraction, sender_hourly_counts()
  utils.py         to_utc()/local_now()/local_hour_bucket() (zoneinfo-based timezone conversion), parse_list(), CSV/log sanitization
  clients/
    base.py        Shared HTTP plumbing: request pacing, error normalization
    events.py      Mailgun Events API client (pagination via `paging.next`)
    mock.py        Realistic sample events for mock mode
  ui/
    shared.py       CSS, sidebar (mode badge, configured domains), session state
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
`config.py`, `utils.py`) — no network access, no Streamlit runtime needed.

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
