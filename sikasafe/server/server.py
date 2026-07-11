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
RATE_PER_HOUR = int(os.environ.get("SIKA_RATE_PER_HOUR", "20"))    # reports/reporter/hour
NOTE_MAX = 280
CATEGORIES = {"reverse", "agent", "promo", "code", "simswap", "fee", "other"}

_SALT = os.environ.get("SIKA_SALT", "sikasafe-reporter-salt-v1").encode()


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
                 created_at REAL NOT NULL,
                 UNIQUE(number, reporter)
               )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_number ON reports(number)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reporter ON reports(reporter, created_at)")


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


def mask_number(n: str) -> str:
    return n[:3] + "•••" + n[-3:] if len(n) >= 7 else "•••"


def clean_note(note: str) -> str:
    note = re.sub(r"[\x00-\x1f\x7f]", " ", note or "").strip()
    return note[:NOTE_MAX]


def aggregate(conn, number: str) -> dict:
    rows = conn.execute(
        "SELECT reporter, category, created_at FROM reports WHERE number=?", (number,)
    ).fetchall()
    reporters = {r["reporter"] for r in rows}
    cats: dict = {}
    for r in rows:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    n = len(reporters)
    status = "flagged" if n >= FLAG_THRESHOLD else "watch" if n >= 1 else "clean"
    return {
        "number": number,
        "reporters": n,
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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _client_ip(self) -> str:
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() if fwd else (self.client_address[0] or "0.0.0.0")

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
                    "HAVING COUNT(DISTINCT reporter) >= ?)", (FLAG_THRESHOLD,)
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
                    "ORDER BY last DESC LIMIT 20", (FLAG_THRESHOLD,)
                ).fetchall()
            return self._json({"recent": [
                {"number": mask_number(r["number"]), "reporters": r["reporters"], "last_reported": r["last"]}
                for r in rows
            ]})
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        if urlparse(self.path).path != "/api/report":
            return self._json({"error": "not found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 4096:
                return self._json({"error": "payload too large"}, 413)
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json({"error": "bad json"}, 400)

        number = normalize_number(data.get("number", ""))
        if not number:
            return self._json({"error": "invalid Ghana mobile number"}, 400)
        category = data.get("category", "other")
        if category not in CATEGORIES:
            category = "other"
        note = clean_note(data.get("note", ""))
        rep = reporter_id(data.get("client_id", ""), self._client_ip())

        with db() as conn:
            recent = conn.execute(
                "SELECT COUNT(*) c FROM reports WHERE reporter=? AND created_at > ?",
                (rep, time.time() - 3600),
            ).fetchone()["c"]
            if recent >= RATE_PER_HOUR:
                return self._json({"error": "rate limit reached, try later"}, 429)
            conn.execute(
                "INSERT OR IGNORE INTO reports(number, category, note, reporter, created_at) "
                "VALUES(?,?,?,?,?)", (number, category, note, rep, time.time()),
            )
            conn.commit()
            agg = aggregate(conn, number)
        agg["thanks"] = True
        return self._json(agg, 201)


def make_server(port=PORT):
    init_db()
    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


if __name__ == "__main__":
    srv = make_server()
    print(f"SikaSafe community backend on :{srv.server_address[1]}  (db={DB_PATH}, "
          f"flag>={FLAG_THRESHOLD} reporters)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
