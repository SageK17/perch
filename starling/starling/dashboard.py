"""
Generates a single self-contained HTML dashboard from vault stats.

No server, no dependencies, no external requests -- just a static file you can
open in any browser (or, in this repo's spirit, host free on GitHub Pages). It
visualises pooled capacity, per-provider usage, the dedup/compression win, and
the redundancy policy.
"""

from __future__ import annotations

import html
from typing import Dict


def _fmt_bytes(n: float) -> str:
    # Decimal units, matching the CLI and how providers advertise capacity.
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1000 or unit == "PB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1000
    return f"{n:.2f} PB"


def render(stats: Dict, vault_name: str = "vault") -> str:
    prov_rows = []
    for p in stats["providers"]:
        cap = p["capacity"]
        used = p["used"]
        pct = (used / cap * 100) if cap else 0
        cap_txt = _fmt_bytes(cap) if cap else "unmetered"
        health = {True: "ok", False: "down", None: "—"}[p["healthy"]]
        prov_rows.append(
            f"""<tr>
  <td><span class="dot {health}"></span>{html.escape(p['id'])}</td>
  <td class="kind">{html.escape(p['kind'])}</td>
  <td>{_fmt_bytes(used)}</td>
  <td>{cap_txt}</td>
  <td><div class="bar"><div class="fill" style="width:{min(100, pct):.1f}%"></div></div></td>
</tr>"""
        )

    logical = stats["logical_bytes"]
    stored = stats["stored_bytes"]
    dedup = stats["dedup_ratio"]
    saved = max(0, logical - stats["unique_bytes"])

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Starling · {html.escape(vault_name)}</title>
<style>
  :root {{ --bg:#0f1512; --card:#17201c; --line:#26332c; --ink:#e7f2ec;
          --mut:#8fa89b; --acc:#39d3a0; --warn:#e8b04a; --bad:#e2603b; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;
         background:var(--bg); color:var(--ink); padding:32px; }}
  h1 {{ font-size:22px; margin:0 0 2px; }}
  h1 .s {{ color:var(--acc); }}
  .sub {{ color:var(--mut); margin-bottom:24px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
          gap:14px; margin-bottom:24px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:14px;
          padding:16px 18px; }}
  .card .k {{ color:var(--mut); font-size:12px; text-transform:uppercase;
             letter-spacing:.04em; }}
  .card .v {{ font-size:26px; font-weight:650; margin-top:6px; }}
  .card .v small {{ font-size:14px; color:var(--mut); font-weight:400; }}
  table {{ width:100%; border-collapse:collapse; background:var(--card);
          border:1px solid var(--line); border-radius:14px; overflow:hidden; }}
  th,td {{ text-align:left; padding:11px 14px; border-bottom:1px solid var(--line); }}
  th {{ color:var(--mut); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
  tr:last-child td {{ border-bottom:none; }}
  .kind {{ color:var(--mut); }}
  .bar {{ background:#0c110e; border-radius:6px; height:9px; width:130px; overflow:hidden; }}
  .fill {{ background:linear-gradient(90deg,var(--acc),#2aa88a); height:100%; }}
  .dot {{ display:inline-block; width:8px; height:8px; border-radius:50%;
         margin-right:8px; background:var(--mut); }}
  .dot.ok {{ background:var(--acc); }} .dot.down {{ background:var(--bad); }}
  .foot {{ color:var(--mut); font-size:12px; margin-top:20px; }}
  .pill {{ display:inline-block; background:#12281f; color:var(--acc);
          border:1px solid #1e4535; border-radius:999px; padding:3px 12px;
          font-size:13px; }}
</style></head><body>
  <h1><span class="s">✦</span> Starling — {html.escape(vault_name)}</h1>
  <div class="sub">A murmuration of free clouds acting as one encrypted drive.</div>

  <div class="grid">
    <div class="card"><div class="k">Logical data</div>
      <div class="v">{_fmt_bytes(logical)}</div></div>
    <div class="card"><div class="k">Physically stored</div>
      <div class="v">{_fmt_bytes(stored)}</div></div>
    <div class="card"><div class="k">Dedup ratio</div>
      <div class="v">{dedup:.2f}× <small>({_fmt_bytes(saved)} saved)</small></div></div>
    <div class="card"><div class="k">Files · chunks</div>
      <div class="v">{stats['files']} <small>· {stats['chunks']}</small></div></div>
    <div class="card"><div class="k">Pooled capacity</div>
      <div class="v">{_fmt_bytes(stats['pooled_capacity'])}</div></div>
    <div class="card"><div class="k">Usable (after redundancy)</div>
      <div class="v">{_fmt_bytes(stats['usable_capacity'])}</div></div>
  </div>

  <div style="margin-bottom:14px"><span class="pill">{html.escape(stats['policy'])}</span></div>

  <table>
    <thead><tr><th>Provider</th><th>Kind</th><th>Used</th><th>Capacity</th><th>Fill</th></tr></thead>
    <tbody>
      {''.join(prov_rows) or '<tr><td colspan="5">No providers yet.</td></tr>'}
    </tbody>
  </table>

  <div class="foot">Generated by Starling. All figures are computed locally;
    providers hold only encrypted, opaque-named blobs.</div>
</body></html>"""
