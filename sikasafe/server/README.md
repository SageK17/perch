# SikaSafe community backend

A tiny, **dependency-free** API (Python standard library + SQLite) that turns the
app's on-phone scam reports into a **shared, community-wide blocklist**. Optional:
SikaSafe works fully offline without it; point the app at this server to unlock
community lookups.

## Run it

```bash
cd server
python3 server.py          # listens on $PORT (default 8791)
```

Then open the app with the API configured (see the app's `js/api.js`
`SIKA_API`, or set `localStorage['sikasafe.api'] = 'https://your-host'`).

## API

| Method | Path | Body / query | Returns |
| --- | --- | --- | --- |
| `GET`  | `/api/health` | — | `{ok, threshold}` |
| `GET`  | `/api/lookup` | `?number=0244…` | aggregate for a number |
| `POST` | `/api/report` | `{number, category, note, client_id}` | updated aggregate |
| `GET`  | `/api/stats` | — | `{total_reports, numbers, flagged, categories}` |
| `GET`  | `/api/recent` | — | recently flagged numbers (masked) |

A lookup aggregate looks like:

```json
{ "number": "0244123456", "reporters": 3, "reports": 4,
  "categories": {"reverse": 2, "agent": 2}, "status": "flagged", "threshold": 3 }
```

`status` is `clean` (0 reporters), `watch` (1–2), or `flagged` (≥ `threshold`).

## What keeps a public, unauthenticated service honest

- **Distinct-reporter threshold** — a number is only shown as *flagged* once
  several different people report it, so one malicious report can't brand a
  number. 1–2 reports show as *watch*.
- **Per-reporter de-duplication** — a client can't inflate a count by reporting
  the same number twice (`UNIQUE(number, reporter)`).
- **Privacy** — reporter identity is a salted hash of (client id + IP), never
  stored raw; free-text notes are kept only for moderation and are **never**
  returned by lookup (no PII / defamation surface).
- **Write rate limiting** per reporter (`SIKA_RATE_PER_HOUR`).
- **Validation** — only well-formed Ghana mobile numbers are accepted.

## Configuration (environment variables)

| Var | Default | Meaning |
| --- | --- | --- |
| `PORT` | `8791` | listen port |
| `SIKA_DB` | `sikasafe.db` | SQLite file path |
| `SIKA_FLAG_THRESHOLD` | `3` | distinct reporters to reach `flagged` |
| `SIKA_RATE_PER_HOUR` | `20` | reports per reporter per hour |
| `SIKA_SALT` | (built-in) | **set your own** — salts reporter hashes |

## Deploy free

Any host that runs Python works — no build, no dependencies:

- **Render / Railway / Fly.io** — set the service root to `server/`, start
  command `python3 server.py`. A `Procfile` is included.
- **Persistence:** SQLite lives in one file. On platforms with ephemeral disks,
  attach a **persistent volume** and set `SIKA_DB` to a path on it, or move to a
  managed DB (Postgres / Turso) — the storage layer is small and isolated in
  `server.py`.

## Honest limits

This is a solid foundation, not a hardened production service. For real scale
you'd add: moderation tooling and appeals (numbers can be disputed), a CAPTCHA
or attestation to slow mass poisoning, and a durable database. The threshold +
dedup + rate limit are the first line of defence, not the last.

## Tests

```bash
python3 server/test_server.py     # report/dedup/threshold/rate-limit/validation
```
