#!/usr/bin/env python3
"""
SikaSafe community backend — a shared scam-number blocklist.

A tiny, dependency-free API (Python standard library + SQLite) that turns the
app's on-phone reports into a shared, community-wide warning list:

    POST /api/report   {number, category, note, client_id}  -> aggregate
    GET  /api/lookup?number=0244...                          -> aggregate
    GET  /api/stats                                          -> community totals
    GET  /api/recent                                         -> recently flagged (masked)
    GET  /api/health

Design choices that keep a public, unauthenticated service honest:

  * A number is only shown as "flagged" once several DISTINCT people report it
    (a threshold), so one malicious report can't brand a number. 1-2 reports =
    "watch".
  * Reports are de-duplicated per reporter — a single client can't inflate a
    count by reporting the same number repeatedly.
  * Reporter identity is a hash of (client id + IP), never stored raw; free-text
    notes are kept only for moderation and never returned by lookup (avoids
    leaking PII / defamation surface).
  * Per-reporter write rate limiting.
  * Numbers are validated as Ghana mobile numbers and normalised.

Runs anywhere Python runs (Render, Railway, Fly.io, a VPS). No build, no deps.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# ---- config (override via environment) -------------------------------------
DB_PATH = os.environ.get("SIKA_DB", "sikasafe.db")
PORT = int(os.environ.get("PORT", "8791"))
FLAG_THRESHOLD = int(os.environ.get("SIKA_FLAG_THRESHOLD", "3"))   # distinct reporters
MIN_NETWORKS = int(os.environ.get("SIKA_MIN_NETWORKS", "2"))       # distinct IPs to flag
RATE_PER_HOUR = int(os.environ.get("SIKA_RATE_PER_HOUR", "20"))    # reports/reporter/hour
RATE_PER_IP = int(os.environ.get("SIKA_RATE_PER_IP", "60"))        # reports/IP/hour
DISPUTE_RATE_PER_IP = int(os.environ.get("SIKA_DISPUTE_RATE_PER_IP", "10"))  # disputes/IP/hour
NOTE_MAX = 280
CATEGORIES = {"reverse", "agent", "promo", "code", "simswap", "fee", "other"}

_SALT = os.environ.get("SIKA_SALT", "sikasafe-reporter-salt-v1").encode()

# CORS: lock to your app's origin in production (e.g. https://sikasafe.pages.dev).
# "*" keeps the community API openly readable, which is a defensible default for
# a public-good blocklist, but set SIKA_ALLOW_ORIGIN once you have a domain.
ALLOW_ORIGIN = os.environ.get("SIKA_ALLOW_ORIGIN", "*")

# Number of proxy hops your platform puts in front of this app (Render/Railway/
# Fly all add exactly one load-balancer hop). The client IP is read from that
# many entries in from the RIGHT of X-Forwarded-For — the only part your proxy
# controls. A client can forge the left of XFF, so trusting it would let one
# machine fake many "networks" and defeat the anti-poisoning rule. Set to 0 only
# when the app is exposed directly with no proxy (uses the socket IP).
TRUSTED_PROXY_HOPS = int(os.environ.get("SIKA_TRUSTED_PROXY_HOPS", "1"))

# Bearer token for /api/admin/* (moderation). Admin routes are DISABLED unless
# this is set. Generate a long random value and keep it secret.
ADMIN_TOKEN = os.environ.get("SIKA_ADMIN_TOKEN", "")


# ---- storage ---------------------------------------------------------------
def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS reports (
                 id INTEGER PRIMARY KEY,
                 number TEXT NOT NULL,
                 category TEXT NOT NULL,
                 note TEXT,
                 reporter TEXT NOT NULL,
                 ip_hash TEXT NOT NULL DEFAULT '',
                 created_at REAL NOT NULL,
                 UNIQUE(number, reporter)
               )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_number ON reports(number)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reporter ON reports(reporter, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_iphash ON reports(ip_hash, created_at)")
        # Numbers a moderator has reviewed and cleared (e.g. a real business or
        # short code wrongly reported). Whitelisted numbers always look up as
        # "cleared" and cannot be re-reported.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS whitelist (
                 number TEXT PRIMARY KEY,
                 reason TEXT,
                 created_at REAL NOT NULL
               )"""
        )
        # Someone contesting a flag on a number, queued for moderator review.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS disputes (
                 id INTEGER PRIMARY KEY,
                 number TEXT NOT NULL,
                 reason TEXT,
                 contact TEXT,
                 ip_hash TEXT NOT NULL DEFAULT '',
                 created_at REAL NOT NULL,
                 resolved INTEGER NOT NULL DEFAULT 0
               )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_disputes ON disputes(resolved, created_at)")


# ---- helpers ---------------------------------------------------------------
def normalize_number(raw: str):
    """Return a normalised Ghana mobile number, or None if it isn't one."""
    n = re.sub(r"[^\d+]", "", raw or "")
    n = re.sub(r"^\+?233", "0", n)
    if len(n) == 9 and not n.startswith("0"):
        n = "0" + n
    # Ghana mobile: 10 digits, 0 + [2 or 5] + 8 digits (MTN/Telecel/AirtelTigo ranges)
    if re.fullmatch(r"0[25]\d{8}", n):
        return n
    return None


def reporter_id(client_id: str, ip: str) -> str:
    return hashlib.sha256(_SALT + (client_id or "").encode() + b"|" + ip.encode()).hexdigest()[:32]


def ip_id(ip: str) -> str:
    return hashlib.sha256(_SALT + b"ip|" + ip.encode()).hexdigest()[:32]


def mask_number(n: str) -> str:
    return n[:3] + "•••" + n[-3:] if len(n) >= 7 else "•••"


def clean_note(note: str) -> str:
    note = re.sub(r"[\x00-\x1f\x7f]", " ", note or "").strip()
    return note[:NOTE_MAX]


def is_whitelisted(conn, number: str) -> bool:
    return conn.execute("SELECT 1 FROM whitelist WHERE number=?", (number,)).fetchone() is not None


def aggregate(conn, number: str) -> dict:
    # A cleared number never carries reports (they're deleted on whitelisting and
    # new ones are blocked), so it always reads as reviewed-and-safe.
    if is_whitelisted(conn, number):
        return {
            "number": number, "reporters": 0, "networks": 0, "reports": 0,
            "categories": {}, "last_reported": None, "status": "cleared",
            "threshold": FLAG_THRESHOLD,
        }
    rows = conn.execute(
        "SELECT reporter, ip_hash, category, created_at FROM reports WHERE number=?", (number,)
    ).fetchall()
    reporters = {r["reporter"] for r in rows}
    networks = {r["ip_hash"] for r in rows if r["ip_hash"]}
    cats: dict = {}
    for r in rows:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    n, nets = len(reporters), len(networks)
    # Flag only with enough distinct reporters AND across enough distinct
    # networks, so one machine rotating client ids can't brand a number.
    if n >= FLAG_THRESHOLD and nets >= MIN_NETWORKS:
        status = "flagged"
    elif n >= 1:
        status = "watch"
    else:
        status = "clean"
    return {
        "number": number,
        "reporters": n,
        "networks": nets,
        "reports": len(rows),
        "categories": cats,
        "last_reported": max((r["created_at"] for r in rows), default=None),
        "status": status,
        "threshold": FLAG_THRESHOLD,
    }


# ---- HTTP handler ----------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "SikaSafe/1.0"

    # -- plumbing --
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        if ALLOW_ORIGIN != "*":
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _client_ip(self) -> str:
        # Trust only the hops our own proxy appends (the RIGHT of the list); the
        # left is client-supplied and forgeable. See TRUSTED_PROXY_HOPS above.
        fwd = [p.strip() for p in self.headers.get("X-Forwarded-For", "").split(",") if p.strip()]
        if TRUSTED_PROXY_HOPS > 0 and len(fwd) >= TRUSTED_PROXY_HOPS:
            return fwd[-TRUSTED_PROXY_HOPS]
        return self.client_address[0] or "0.0.0.0"

    def _is_admin(self) -> bool:
        if not ADMIN_TOKEN:
            return False
        auth = self.headers.get("Authorization", "")
        tok = auth[7:] if auth.startswith("Bearer ") else ""
        return bool(tok) and hmac.compare_digest(tok, ADMIN_TOKEN)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def log_message(self, *a):
        pass

    # -- routes --
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/api/health":
            return self._json({"ok": True, "threshold": FLAG_THRESHOLD})
        if u.path == "/api/lookup":
            number = normalize_number((q.get("number", [""])[0]))
            if not number:
                return self._json({"error": "invalid number"}, 400)
            with db() as conn:
                return self._json(aggregate(conn, number))
        if u.path == "/api/stats":
            with db() as conn:
                total = conn.execute("SELECT COUNT(*) c FROM reports").fetchone()["c"]
                numbers = conn.execute("SELECT COUNT(DISTINCT number) c FROM reports").fetchone()["c"]
                flagged = conn.execute(
                    "SELECT COUNT(*) c FROM (SELECT number FROM reports GROUP BY number "
                    "HAVING COUNT(DISTINCT reporter) >= ? AND COUNT(DISTINCT ip_hash) >= ?)",
                    (FLAG_THRESHOLD, MIN_NETWORKS)
                ).fetchone()["c"]
                cats = conn.execute(
                    "SELECT category, COUNT(*) c FROM reports GROUP BY category ORDER BY c DESC"
                ).fetchall()
            return self._json({
                "total_reports": total, "numbers": numbers, "flagged": flagged,
                "categories": {r["category"]: r["c"] for r in cats},
            })
        if u.path == "/api/recent":
            with db() as conn:
                rows = conn.execute(
                    "SELECT number, COUNT(DISTINCT reporter) reporters, MAX(created_at) last "
                    "FROM reports GROUP BY number HAVING reporters >= ? "
                    "AND COUNT(DISTINCT ip_hash) >= ? ORDER BY last DESC LIMIT 20",
                    (FLAG_THRESHOLD, MIN_NETWORKS)
                ).fetchall()
            return self._json({"recent": [
                {"number": mask_number(r["number"]), "reporters": r["reporters"], "last_reported": r["last"]}
                for r in rows
            ]})
        if u.path == "/api/admin/disputes":
            if not ADMIN_TOKEN:
                return self._json({"error": "not found"}, 404)
            if not self._is_admin():
                return self._json({"error": "unauthorized"}, 401)
            with db() as conn:
                rows = conn.execute(
                    "SELECT id, number, reason, contact, created_at FROM disputes "
                    "WHERE resolved=0 ORDER BY created_at DESC LIMIT 200"
                ).fetchall()
                out = []
                for r in rows:
                    agg = aggregate(conn, r["number"])
                    out.append({
                        "id": r["id"], "number": r["number"], "reason": r["reason"],
                        "contact": r["contact"], "created_at": r["created_at"],
                        "current_status": agg["status"], "reporters": agg["reporters"],
                    })
            return self._json({"disputes": out})
        return self._json({"error": "not found"}, 404)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 4096:
            raise ValueError("payload too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self._read_json()
        except ValueError:
            return self._json({"error": "payload too large"}, 413)
        except Exception:
            return self._json({"error": "bad json"}, 400)
        if not isinstance(data, dict):
            return self._json({"error": "bad json"}, 400)

        if path == "/api/report":
            return self._report(data)
        if path == "/api/dispute":
            return self._dispute(data)
        if path in ("/api/admin/remove", "/api/admin/whitelist", "/api/admin/unwhitelist"):
            return self._admin(path, data)
        return self._json({"error": "not found"}, 404)

    def _report(self, data):
        number = normalize_number(data.get("number", ""))
        if not number:
            return self._json({"error": "invalid Ghana mobile number"}, 400)
        category = data.get("category", "other")
        if category not in CATEGORIES:
            category = "other"
        note = clean_note(data.get("note", ""))
        ip = self._client_ip()
        rep = reporter_id(data.get("client_id", ""), ip)
        iph = ip_id(ip)

        with db() as conn:
            # A moderator-cleared number is accepted quietly but never counted.
            if is_whitelisted(conn, number):
                agg = aggregate(conn, number)
                agg["thanks"] = True
                return self._json(agg, 200)
            recent = conn.execute(
                "SELECT COUNT(*) c FROM reports WHERE reporter=? AND created_at > ?",
                (rep, time.time() - 3600),
            ).fetchone()["c"]
            if recent >= RATE_PER_HOUR:
                return self._json({"error": "rate limit reached, try later"}, 429)
            ip_recent = conn.execute(
                "SELECT COUNT(*) c FROM reports WHERE ip_hash=? AND created_at > ?",
                (iph, time.time() - 3600),
            ).fetchone()["c"]
            if ip_recent >= RATE_PER_IP:
                return self._json({"error": "rate limit reached, try later"}, 429)
            conn.execute(
                "INSERT OR IGNORE INTO reports(number, category, note, reporter, ip_hash, created_at) "
                "VALUES(?,?,?,?,?,?)", (number, category, note, rep, iph, time.time()),
            )
            conn.commit()
            agg = aggregate(conn, number)
        agg["thanks"] = True
        return self._json(agg, 201)

    def _dispute(self, data):
        """A wrongly-flagged party contests a number; queued for moderator review."""
        number = normalize_number(data.get("number", ""))
        if not number:
            return self._json({"error": "invalid Ghana mobile number"}, 400)
        reason = clean_note(data.get("reason", ""))
        contact = clean_note(data.get("contact", ""))[:120]
        iph = ip_id(self._client_ip())
        with db() as conn:
            recent = conn.execute(
                "SELECT COUNT(*) c FROM disputes WHERE ip_hash=? AND created_at > ?",
                (iph, time.time() - 3600),
            ).fetchone()["c"]
            if recent >= DISPUTE_RATE_PER_IP:
                return self._json({"error": "rate limit reached, try later"}, 429)
            conn.execute(
                "INSERT INTO disputes(number, reason, contact, ip_hash, created_at) VALUES(?,?,?,?,?)",
                (number, reason, contact, iph, time.time()),
            )
            conn.commit()
        return self._json({"ok": True, "received": True}, 201)

    def _admin(self, path, data):
        if not ADMIN_TOKEN:
            return self._json({"error": "not found"}, 404)
        if not self._is_admin():
            return self._json({"error": "unauthorized"}, 401)
        number = normalize_number(data.get("number", ""))
        if not number:
            return self._json({"error": "invalid Ghana mobile number"}, 400)
        with db() as conn:
            if path == "/api/admin/remove":
                cur = conn.execute("DELETE FROM reports WHERE number=?", (number,))
                conn.commit()
                return self._json({"ok": True, "number": number, "removed": cur.rowcount})
            if path == "/api/admin/whitelist":
                reason = clean_note(data.get("reason", ""))
                conn.execute("DELETE FROM reports WHERE number=?", (number,))
                conn.execute(
                    "INSERT INTO whitelist(number, reason, created_at) VALUES(?,?,?) "
                    "ON CONFLICT(number) DO UPDATE SET reason=excluded.reason",
                    (number, reason, time.time()),
                )
                conn.execute("UPDATE disputes SET resolved=1 WHERE number=?", (number,))
                conn.commit()
                return self._json({"ok": True, "number": number, "status": "cleared"})
            if path == "/api/admin/unwhitelist":
                cur = conn.execute("DELETE FROM whitelist WHERE number=?", (number,))
                conn.commit()
                return self._json({"ok": True, "number": number, "removed": cur.rowcount})
        return self._json({"error": "not found"}, 404)


def make_server(port=PORT):
    init_db()
    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


if __name__ == "__main__":
    srv = make_server()
    print(f"SikaSafe community backend on :{srv.server_address[1]}  (db={DB_PATH}, "
          f"flag>={FLAG_THRESHOLD} reporters/{MIN_NETWORKS} networks, "
          f"proxy_hops={TRUSTED_PROXY_HOPS}, admin={'on' if ADMIN_TOKEN else 'off'})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
