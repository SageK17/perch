# SikaSafe community backend

A tiny, **dependency-free** API (Python standard library + SQLite) that turns the
app's on-phone scam reports into a **shared, community-wide blocklist**. It is
optional: SikaSafe works fully offline without it; point the app at this server
to unlock community lookups.

## Run it locally

```bash
cd server
python3 server.py          # listens on $PORT (default 8791)
```

Then open the app with the API configured — set it from the app's **Reports →
Community server** panel, or `localStorage['sikasafe.api'] = 'https://your-host'`,
or bake a default into `js/api.js` (`DEFAULT_API`).

## API

| Method | Path | Body / query | Returns |
| --- | --- | --- | --- |
| `GET`  | `/api/health` | — | `{ok, threshold}` |
| `GET`  | `/api/lookup` | `?number=0244…` | aggregate for a number |
| `POST` | `/api/report` | `{number, category, note, client_id}` | updated aggregate |
| `POST` | `/api/dispute` | `{number, reason, contact?}` | `{ok}` — queues a contested flag |
| `GET`  | `/api/stats` | — | `{total_reports, numbers, flagged, categories}` |
| `GET`  | `/api/recent` | — | recently flagged numbers (masked) |

A lookup aggregate looks like:

```json
{ "number": "0244123456", "reporters": 3, "networks": 3, "reports": 4,
  "categories": {"reverse": 2, "agent": 2}, "status": "flagged", "threshold": 3 }
```

`status` is `clean` (0 reporters), `watch` (1–2), `flagged` (≥ threshold across
enough networks), or `cleared` (a moderator reviewed and whitelisted it).

### Moderation (admin) — requires `SIKA_ADMIN_TOKEN`

Admin routes are **disabled** unless `SIKA_ADMIN_TOKEN` is set, and require an
`Authorization: Bearer <token>` header. They exist so a real business or short
code that gets wrongly reported has a way out.

| Method | Path | Body | Effect |
| --- | --- | --- | --- |
| `GET`  | `/api/admin/disputes` | — | list open disputes with each number's current status |
| `POST` | `/api/admin/remove` | `{number}` | delete all reports for a number |
| `POST` | `/api/admin/whitelist` | `{number, reason?}` | clear a number: delete its reports, block new ones, resolve its disputes |
| `POST` | `/api/admin/unwhitelist` | `{number}` | undo a whitelist |

```bash
# review the queue
curl -H "Authorization: Bearer $SIKA_ADMIN_TOKEN" https://your-host/api/admin/disputes
# clear a wrongly-flagged number
curl -X POST -H "Authorization: Bearer $SIKA_ADMIN_TOKEN" -H 'Content-Type: application/json' \
     -d '{"number":"0244123456","reason":"verified business"}' https://your-host/api/admin/whitelist
```

## What keeps a public, unauthenticated service honest

- **Distinct-reporter threshold** — a number is only shown as *flagged* once
  several different people report it. 1–2 reports show as *watch*.
- **Distinct-network requirement** — flagging also needs reports from several
  different networks, so one machine can't brand a number. The client IP is read
  only from the proxy-controlled part of `X-Forwarded-For` (see
  `SIKA_TRUSTED_PROXY_HOPS`), so a client **cannot forge extra networks** by
  sending its own `X-Forwarded-For` header.
- **Per-reporter de-duplication** — `UNIQUE(number, reporter)` stops count
  inflation from one client.
- **Rate limiting** — per reporter and per IP for reports, and per IP for
  disputes.
- **Privacy** — reporter identity is a salted hash of (client id + IP), never
  stored raw; free-text notes are moderation-only and **never** returned by
  lookup.
- **Moderation & appeals** — anyone can dispute a flag; a moderator can remove
  or whitelist a number.
- **Validation** — only well-formed Ghana mobile numbers are accepted.

## Configuration (environment variables)

| Var | Default | Meaning |
| --- | --- | --- |
| `PORT` | `8791` | listen port |
| `SIKA_DB` | `sikasafe.db` | SQLite file path (put on a **persistent volume**) |
| `SIKA_FLAG_THRESHOLD` | `3` | distinct reporters to reach `flagged` |
| `SIKA_MIN_NETWORKS` | `2` | distinct networks (IPs) also required to `flag` |
| `SIKA_RATE_PER_HOUR` | `20` | reports per reporter per hour |
| `SIKA_RATE_PER_IP` | `60` | reports per IP per hour |
| `SIKA_DISPUTE_RATE_PER_IP` | `10` | disputes per IP per hour |
| `SIKA_TRUSTED_PROXY_HOPS` | `1` | how many proxy hops your host adds to `X-Forwarded-For`; `0` = no proxy (use socket IP) |
| `SIKA_ALLOW_ORIGIN` | `*` | CORS origin — set to your app's URL in production |
| `SIKA_SALT` | (built-in) | **set your own** — salts reporter/IP hashes |
| `SIKA_ADMIN_TOKEN` | (unset) | enables `/api/admin/*`; set a long random secret |

> **Proxy hops matter for security.** Render, Railway, and Fly each put exactly
> **one** load balancer in front of your app, so keep `SIKA_TRUSTED_PROXY_HOPS=1`.
> If you add another proxy (e.g. Cloudflare in front of Fly), increase it to match,
> or the anti-poisoning network count can be spoofed.

## Deploy

The backend is dependency-free, so almost anything works. Persistent storage for
the SQLite file is the one requirement.

### Docker (recommended — includes a volume)

```bash
cd server
docker build -t sikasafe-api .
docker run -p 8791:8791 -v sikasafe_data:/data \
  -e SIKA_SALT="$(openssl rand -hex 32)" \
  -e SIKA_ADMIN_TOKEN="$(openssl rand -hex 32)" \
  -e SIKA_ALLOW_ORIGIN="https://sikasafe.pages.dev" \
  sikasafe-api
```

### Render — `render.yaml` (Blueprint)

Point Render at the repo; it reads `render.yaml`, provisions a 1 GB disk at
`/data`, and generates `SIKA_SALT` / `SIKA_ADMIN_TOKEN`. Set `SIKA_ALLOW_ORIGIN`
to your app URL.

### Fly.io — `fly.toml`

```bash
cd server
fly launch --no-deploy --copy-config
fly volumes create sikasafe_data --size 1 --region jnb
fly secrets set SIKA_SALT="$(openssl rand -hex 32)" \
                SIKA_ADMIN_TOKEN="$(openssl rand -hex 32)" \
                SIKA_ALLOW_ORIGIN="https://sikasafe.pages.dev"
fly deploy
```

A `Procfile` + `runtime.txt` are also included for buildpack platforms — but
those often have **ephemeral disks**, so prefer the Docker/volume path above, or
move `SIKA_DB` to a managed database.

## Backups

```bash
./backup.sh /data/sikasafe.db /data/backups     # safe while the server runs
# cron (daily 02:00): 0 2 * * * /app/backup.sh /data/sikasafe.db /data/backups
```

Keeps the 30 newest compressed snapshots. Test a restore periodically:
`gunzip -c backups/sikasafe-<stamp>.db.gz > restored.db`.

## Privacy & legal

This service stores **third parties' phone numbers** (the numbers people report).
In Ghana that engages the **Data Protection Act, 2012 (Act 843)**: publish a
privacy policy, define a lawful basis and a retention period, and check whether
you must register with the Data Protection Commission **before** operating
publicly. Reporter identities are hashed and notes are never exposed, but the
reported numbers themselves are personal data — handle them accordingly.

## Scaling notes

SQLite + WAL is comfortable at community volume, and the rate-limit counters are
DB-backed so they hold across restarts and multiple instances that share the
same database file. When write volume outgrows a single file, migrate `SIKA_DB`
to Postgres/Turso — the storage layer is small and isolated in `server.py`.

## Tests

```bash
python3 server/test_server.py
# report/dedup/threshold/rate-limit/validation + XFF-spoof/whitelist/admin/dispute
```
