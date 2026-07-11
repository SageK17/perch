"""
Tests for the SikaSafe community backend.

    python3 server/test_server.py

Starts the real server in a thread against a temp DB and drives it over HTTP.
"""

import json
import os
import sys
import tempfile
import threading
import urllib.request

os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402


def _req(base, path, method="GET", body=None, ip=None, token=None):
    url = base + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {}
    if data:
        headers["Content-Type"] = "application/json"
    if ip:
        headers["X-Forwarded-For"] = ip   # simulate the proxy chain / networks
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def run():
    tmp = tempfile.mkdtemp()
    server.DB_PATH = os.path.join(tmp, "test.db")
    server.FLAG_THRESHOLD = 3
    server.MIN_NETWORKS = 2
    server.RATE_PER_HOUR = 3
    server.RATE_PER_IP = 8
    srv = server.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    results = []
    ok = lambda name, cond: results.append(f"{'ok  ' if cond else 'FAIL'} {name}")

    # health
    s, b = _req(base, "/api/health")
    ok("health ok", s == 200 and b["ok"])

    # invalid numbers rejected
    s, _ = _req(base, "/api/report", "POST", {"number": "12345", "client_id": "a"})
    ok("junk number rejected (400)", s == 400)
    s, _ = _req(base, "/api/lookup?number=12345")
    ok("lookup junk rejected (400)", s == 400)

    NUM = "0244123456"
    # first report -> watch, 1 reporter
    s, b = _req(base, "/api/report", "POST", {"number": NUM, "category": "reverse", "client_id": "c1"}, ip="10.0.0.1")
    ok("first report -> 201 watch", s == 201 and b["status"] == "watch" and b["reporters"] == 1)

    # same client again -> deduped (still 1 reporter)
    s, b = _req(base, "/api/report", "POST", {"number": NUM, "category": "reverse", "client_id": "c1"}, ip="10.0.0.1")
    ok("same client deduped (1 reporter)", b["reporters"] == 1)

    # two more distinct clients on distinct networks -> flagged
    _req(base, "/api/report", "POST", {"number": NUM, "category": "agent", "client_id": "c2"}, ip="10.0.0.2")
    s, b = _req(base, "/api/report", "POST", {"number": NUM, "category": "reverse", "client_id": "c3"}, ip="10.0.0.3")
    ok("3 reporters / 3 networks -> flagged", b["status"] == "flagged" and b["reporters"] == 3 and b["networks"] == 3)

    # ANTI-POISONING: many client ids from ONE network stay "watch", never flagged
    POISON = "0247654321"
    for cid in ["p1", "p2", "p3", "p4"]:
        s, b = _req(base, "/api/report", "POST", {"number": POISON, "client_id": cid}, ip="9.9.9.9")
    ok("single-network poisoning stays watch", b["status"] == "watch" and b["reporters"] == 4 and b["networks"] == 1)

    # lookup reflects the aggregate, categories included
    s, b = _req(base, "/api/lookup?number=024%20412%203456")  # spaces normalise
    ok("lookup normalises + flagged", b["status"] == "flagged" and b["categories"].get("reverse") == 2)

    # unreported number -> clean
    s, b = _req(base, "/api/lookup?number=0201111111")
    ok("unknown number -> clean", b["status"] == "clean" and b["reporters"] == 0)

    # notes are never leaked by lookup
    ok("lookup hides notes", "note" not in b and "notes" not in b)

    # per-reporter rate limit: c4 reports 3 distinct numbers ok, 4th -> 429
    for num in ["0245000001", "0245000002", "0245000003"]:
        _req(base, "/api/report", "POST", {"number": num, "client_id": "c4"}, ip="10.5.5.5")
    s, b = _req(base, "/api/report", "POST", {"number": "0245000004", "client_id": "c4"}, ip="10.5.5.5")
    ok("per-reporter rate limit -> 429", s == 429)

    # per-IP rate limit: distinct clients from one IP blocked after RATE_PER_IP
    codes = []
    for i in range(server.RATE_PER_IP + 2):
        s, _ = _req(base, "/api/report", "POST", {"number": f"0259{i:06d}", "client_id": f"f{i}"}, ip="7.7.7.7")
        codes.append(s)
    ok("per-IP flood -> 429", codes[0] == 201 and 429 in codes)

    # stats
    s, b = _req(base, "/api/stats")
    ok("stats: flagged count", b["flagged"] == 1 and b["numbers"] >= 4)

    # recent returns masked flagged numbers
    s, b = _req(base, "/api/recent")
    ok("recent masks numbers", len(b["recent"]) == 1 and "•" in b["recent"][0]["number"])

    # ---- XFF spoofing cannot forge distinct networks (anti-poisoning holds) ----
    # Attacker forges the LEFT of X-Forwarded-For; the trusted proxy appends the
    # real IP on the RIGHT. With TRUSTED_PROXY_HOPS=1 only the right is trusted,
    # so all three reports collapse to ONE network -> stays "watch".
    SPOOF = "0248880001"
    for i in (1, 2, 3):
        s, b = _req(base, "/api/report", "POST",
                    {"number": SPOOF, "category": "agent", "client_id": f"s{i}"},
                    ip=f"9.9.9.{i}, 55.55.55.55")
    ok("XFF spoof stays 1 network / watch", b["status"] == "watch" and b["networks"] == 1)

    # ---- moderation: admin routes require a valid bearer token ----
    server.ADMIN_TOKEN = "test-admin"
    s, _ = _req(base, "/api/admin/disputes")
    ok("admin list without token -> 401", s == 401)
    s, _ = _req(base, "/api/admin/disputes", token="wrong")
    ok("admin list wrong token -> 401", s == 401)
    s, b = _req(base, "/api/admin/disputes", token="test-admin")
    ok("admin list with token -> 200", s == 200 and "disputes" in b)

    # ---- public dispute is recorded and surfaces to the moderator ----
    s, b = _req(base, "/api/dispute", "POST",
                {"number": NUM, "reason": "my real shop line", "contact": "x@y.gh"}, ip="88.0.0.9")
    ok("dispute accepted (201)", s == 201 and b["ok"])
    s, b = _req(base, "/api/admin/disputes", token="test-admin")
    ok("dispute shows in admin queue", any(d["number"] == NUM for d in b["disputes"]))

    # ---- whitelist clears a number and blocks new reports ----
    s, b = _req(base, "/api/admin/whitelist", "POST",
                {"number": NUM, "reason": "verified business"}, token="test-admin")
    ok("admin whitelist -> cleared", s == 200 and b["status"] == "cleared")
    s, b = _req(base, "/api/lookup?number=" + NUM)
    ok("whitelisted lookup -> cleared, 0 reporters", b["status"] == "cleared" and b["reporters"] == 0)
    s, b = _req(base, "/api/report", "POST", {"number": NUM, "client_id": "new1"}, ip="70.0.0.1")
    ok("report on whitelisted stays cleared", b["status"] == "cleared")
    s, b = _req(base, "/api/admin/disputes", token="test-admin")
    ok("whitelist resolves the dispute", all(d["number"] != NUM for d in b["disputes"]))

    server.ADMIN_TOKEN = ""  # leave module state as we found it

    srv.shutdown()
    print("\n".join(results))
    passed = sum(1 for r in results if r.startswith("ok"))
    print(f"\n{passed}/{len(results)} backend tests passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(run())
