"""
Command-line interface for Starling.

    starling init          create a vault (choose a redundancy policy)
    starling provider add  register a storage provider (a free account / folder)
    starling provider ls   list providers
    starling put           upload a file (chunk, dedup, encrypt, distribute)
    starling get           download and reassemble a file
    starling ls            list files in the vault
    starling rm            delete a file (and GC now-unreferenced chunks)
    starling df            pooled capacity, dedup, and redundancy stats
    starling fsck          verify redundancy/integrity; --repair to self-heal
    starling sync          mirror the encrypted manifest to providers (push/pull)
    starling dashboard     write a self-contained HTML status page
    starling optimize      recompress data; --delta also diffs near-duplicates
    starling gc            collect orphaned chunks; --prune stray provider blobs
    starling dict          train/show a shared compression dictionary

The vault passphrase comes from $STARLING_PASSPHRASE, or is prompted for. It is
never written to disk; only a scrypt salt is stored, in config.json.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from typing import List, Optional

from . import __version__
from .dashboard import render as render_dashboard
from .engine import Vault, VaultError
from .placement import NotEnoughProviders, Policy

_UNITS = {
    "": 1, "b": 1,
    "k": 10**3, "kb": 10**3, "kib": 2**10,
    "m": 10**6, "mb": 10**6, "mib": 2**20,
    "g": 10**9, "gb": 10**9, "gib": 2**30,
    "t": 10**12, "tb": 10**12, "tib": 2**40,
}


def parse_size(text: str) -> int:
    s = str(text).strip().lower().replace(" ", "")
    if not s:
        return 0
    i = 0
    while i < len(s) and (s[i].isdigit() or s[i] == "."):
        i += 1
    num, unit = s[:i], s[i:]
    if unit not in _UNITS:
        raise argparse.ArgumentTypeError(f"bad size {text!r} (try 15GB, 500MB, 2GiB)")
    return int(float(num) * _UNITS[unit])


def fmt_size(n: float) -> str:
    # Decimal units (1 GB = 10^9 B) to match parse_size and how providers
    # advertise free tiers, so "--capacity 15GB" also displays as "15.00 GB".
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1000 or unit == "PB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1000
    return f"{n:.2f} PB"


def _passphrase(confirm: bool = False) -> str:
    env = os.environ.get("STARLING_PASSPHRASE")
    if env:
        return env
    if not sys.stdin.isatty():
        raise VaultError("set $STARLING_PASSPHRASE (no terminal to prompt on)")
    pw = getpass.getpass("Vault passphrase: ")
    if confirm and getpass.getpass("Confirm passphrase: ") != pw:
        raise VaultError("passphrases did not match")
    return pw


def _open(args) -> Vault:
    return Vault.open(args.vault, _passphrase())


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_init(args) -> int:
    if args.policy == "erasure":
        policy = Policy(mode="erasure", k=args.k, m=args.m)
    else:
        policy = Policy(mode="replicate", replicas=args.replicas)
    Vault.create(args.vault, _passphrase(confirm=True), policy=policy)
    print(f"Initialised vault at {args.vault}")
    print(f"  redundancy: {policy.describe()}")
    print("Next: add providers with `starling provider add`.")
    return 0


def cmd_provider_add(args) -> int:
    vault = _open(args)
    spec = {"id": args.id, "kind": args.kind, "capacity": parse_size(args.capacity)}
    if args.kind == "local":
        if not args.root:
            raise VaultError("local providers need --root")
        spec["root"] = os.path.abspath(args.root)
    elif args.kind == "s3":
        if not args.bucket:
            raise VaultError("s3 providers need --bucket")
        spec["bucket"] = args.bucket
        spec["region"] = args.region
        spec["prefix"] = args.prefix
        spec["access_key_env"] = args.access_key_env
        spec["secret_key_env"] = args.secret_key_env
        if args.endpoint:
            spec["endpoint_url"] = args.endpoint
        if args.session_token_env:
            spec["session_token_env"] = args.session_token_env
    try:
        vault.add_provider(spec)  # builds the backend, so bad creds/config fail here
    except ValueError as exc:
        raise VaultError(str(exc)) from exc
    cap = fmt_size(spec["capacity"]) if spec["capacity"] else "unmetered"
    print(f"Added provider {args.id!r} ({args.kind}, {cap}).")
    return 0


def cmd_provider_ls(args) -> int:
    vault = _open(args)
    if not vault.backends:
        print("No providers configured.")
        return 0
    for b in vault.backends.values():
        cap = fmt_size(b.capacity) if b.capacity else "unmetered"
        print(f"  {b.id:<16} {b.kind:<8} used {fmt_size(b.used_bytes()):>10}  cap {cap}")
    return 0


def cmd_put(args) -> int:
    vault = _open(args)
    res = vault.put(args.local, args.dest)
    saved = f", {fmt_size(res.dedup_bytes)} deduplicated" if res.dedup_bytes else ""
    print(
        f"Stored {res.path} ({fmt_size(res.size)}): "
        f"{res.chunks} chunks, {res.new_chunks} new{saved}."
    )
    return 0


def cmd_get(args) -> int:
    vault = _open(args)
    n = vault.get(args.path, args.out)
    print(f"Wrote {args.out} ({fmt_size(n)}).")
    return 0


def cmd_ls(args) -> int:
    vault = _open(args)
    rows = vault.ls(args.prefix or "")
    if not rows:
        print("(empty)")
        return 0
    for r in rows:
        print(f"  {fmt_size(r['size']):>10}  {r['chunks']:>4} chunks  {r['path']}")
    print(f"\n{len(rows)} file(s), {fmt_size(sum(r['size'] for r in rows))} logical.")
    return 0


def cmd_rm(args) -> int:
    vault = _open(args)
    print(f"Removed {args.path}." if vault.rm(args.path) else f"No such file: {args.path}")
    return 0


def cmd_df(args) -> int:
    vault = _open(args)
    vault._healthy_ids(refresh=True)
    s = vault.stats()
    print(f"Policy         : {s['policy']}")
    print(f"Files / chunks : {s['files']} / {s['chunks']}")
    print(f"Logical data   : {fmt_size(s['logical_bytes'])}")
    print(f"Unique (dedup) : {fmt_size(s['unique_bytes'])}  ({s['dedup_ratio']:.2f}x dedup)")
    print(f"Stored (phys.) : {fmt_size(s['stored_bytes'])}  "
          f"({s['space_amplification']:.2f}x amplification)")
    print(f"Pooled capacity: {fmt_size(s['pooled_capacity'])}")
    print(f"Usable capacity: {fmt_size(s['usable_capacity'])}  (after redundancy)")
    print("Providers:")
    for p in s["providers"]:
        cap = fmt_size(p["capacity"]) if p["capacity"] else "unmetered"
        health = {True: "ok", False: "DOWN", None: "?"}[p["healthy"]]
        print(f"  {p['id']:<16} {p['kind']:<8} {health:<4} "
              f"used {fmt_size(p['used']):>10}  cap {cap}")
    return 0


def cmd_fsck(args) -> int:
    vault = _open(args)
    r = vault.fsck(repair=args.repair, deep=args.deep)
    print(f"Checked {r['checked']} chunks: {r['healthy']} healthy, "
          f"{r['degraded']} degraded, {r['lost']} lost.")
    if args.repair:
        print(f"Repaired {r['repaired']} degraded chunk(s).")
    for issue in r["issues"][:20]:
        print(f"  [{issue['state']}] chunk {issue['chunk']} "
              f"{issue['present']}/{issue['of']} copies present")
    return 1 if r["lost"] else 0


def cmd_sync(args) -> int:
    vault = _open(args)
    if args.direction == "push":
        n = vault.sync_push()
        print(f"Pushed encrypted manifest backup to {n} provider(s).")
    else:
        ok = vault.sync_pull()
        print("Restored manifest from a provider backup." if ok
              else "No manifest backup found on any provider.")
    return 0


def _iter_sample_files(path: str):
    if os.path.isdir(path):
        for root, _dirs, files in os.walk(path):
            for name in files:
                yield os.path.join(root, name)
    else:
        yield path


def cmd_dict_train(args) -> int:
    vault = _open(args)
    samples = []
    if args.paths:
        for p in args.paths:
            for f in _iter_sample_files(p):
                try:
                    with open(f, "rb") as fh:
                        samples.append(fh.read())
                except OSError:
                    pass
        src = f"{len(samples)} sample file(s)"
    else:
        samples = vault.sample_chunk_plaintexts()
        src = f"{len(samples)} existing chunk(s)"
    info = vault.train_dictionary(samples)
    print(f"Trained shared dictionary {info['id']} ({fmt_size(info['size'])}) from {src}.")
    print("New writes will use it automatically.")
    if args.recompress:
        r = vault.recompress_all()
        saved = r["before"] - r["after"]
        print(f"Recompressed {r['chunks']} chunk(s): {fmt_size(r['before'])} -> "
              f"{fmt_size(r['after'])} stored ({fmt_size(saved)} saved).")
    return 0


def cmd_dict_show(args) -> int:
    vault = _open(args)
    did = vault.manifest.active_dict
    if not did:
        print("No shared dictionary set. Train one with `starling dict train`.")
        return 0
    users = sum(1 for c in vault.manifest.chunks.values() if c.get("dict") == did)
    size = len(vault.manifest.dictionaries.get(did, b""))
    print(f"Active dictionary : {did} ({fmt_size(size)})")
    print(f"Chunks using it   : {users}/{len(vault.manifest.chunks)}")
    print(f"Dictionaries kept : {len(vault.manifest.dictionaries)}")
    return 0


def cmd_optimize(args) -> int:
    vault = _open(args)
    r = vault.recompress_all()
    saved = r["before"] - r["after"]
    pct = (saved / r["before"] * 100) if r["before"] else 0
    print(f"Recompressed {r['chunks']} chunk(s) with the best available codec.")
    print(f"Stored: {fmt_size(r['before'])} -> {fmt_size(r['after'])} "
          f"({fmt_size(saved)} saved, {pct:.1f}%).")
    if args.delta:
        d = vault.delta_compact()
        dsaved = d["before"] - d["after"]
        dpct = (dsaved / d["before"] * 100) if d["before"] else 0
        print(f"Delta-compressed {d['converted']} near-duplicate chunk(s).")
        print(f"Stored: {fmt_size(d['before'])} -> {fmt_size(d['after'])} "
              f"({fmt_size(dsaved)} saved, {dpct:.1f}%).")
    return 0


def cmd_gc(args) -> int:
    vault = _open(args)
    r = vault.gc(prune_blobs=args.prune)
    print(f"Collected {r['removed']} orphaned chunk(s), freed {fmt_size(r['freed'])}.")
    if args.prune:
        print(f"Pruned {r['pruned']} stray provider blob(s).")
    return 0


def cmd_dashboard(args) -> int:
    vault = _open(args)
    vault._healthy_ids(refresh=True)
    html = render_dashboard(vault.stats(), vault_name=os.path.basename(os.path.abspath(args.vault)))
    with open(args.out, "w") as fh:
        fh.write(html)
    print(f"Wrote dashboard to {args.out}")
    return 0


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="starling", description="A murmuration of free clouds as one encrypted drive.")
    p.add_argument("--version", action="version", version=f"starling {__version__}")
    p.add_argument("--vault", default=os.environ.get("STARLING_VAULT", "./starling-vault"),
                   help="vault directory (default ./starling-vault or $STARLING_VAULT)")
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("init", help="create a new vault")
    q.add_argument("--policy", choices=["replicate", "erasure"], default="replicate")
    q.add_argument("--replicas", type=int, default=3, help="copies per chunk (replicate mode)")
    q.add_argument("-k", type=int, default=4, help="data shards (erasure mode)")
    q.add_argument("-m", type=int, default=2, help="parity shards (erasure mode)")
    q.set_defaults(func=cmd_init)

    prov = sub.add_parser("provider", help="manage storage providers")
    psub = prov.add_subparsers(dest="pcmd", required=True)
    pa = psub.add_parser("add", help="register a provider")
    pa.add_argument("--id", required=True)
    pa.add_argument("--kind", choices=["local", "memory", "s3"], default="local")
    pa.add_argument("--root", help="directory (for kind=local)")
    pa.add_argument("--capacity", default="0", help="free-tier size, e.g. 15GB")
    # s3 options (credentials come from env vars, never stored in config)
    pa.add_argument("--bucket", help="bucket name (for kind=s3)")
    pa.add_argument("--endpoint", help="S3 endpoint URL for R2/B2/MinIO (omit for AWS)")
    pa.add_argument("--region", default="us-east-1", help="S3 region")
    pa.add_argument("--prefix", default="starling/", help="key prefix within the bucket")
    pa.add_argument("--access-key-env", default="AWS_ACCESS_KEY_ID",
                    help="env var holding the access key")
    pa.add_argument("--secret-key-env", default="AWS_SECRET_ACCESS_KEY",
                    help="env var holding the secret key")
    pa.add_argument("--session-token-env", default="",
                    help="optional env var holding a session token")
    pa.set_defaults(func=cmd_provider_add)
    pl = psub.add_parser("ls", help="list providers")
    pl.set_defaults(func=cmd_provider_ls)

    q = sub.add_parser("put", help="upload a file")
    q.add_argument("local")
    q.add_argument("dest", nargs="?", help="vault path (default: basename)")
    q.set_defaults(func=cmd_put)

    q = sub.add_parser("get", help="download a file")
    q.add_argument("path")
    q.add_argument("out")
    q.set_defaults(func=cmd_get)

    q = sub.add_parser("ls", help="list files")
    q.add_argument("prefix", nargs="?", default="")
    q.set_defaults(func=cmd_ls)

    q = sub.add_parser("rm", help="delete a file")
    q.add_argument("path")
    q.set_defaults(func=cmd_rm)

    q = sub.add_parser("df", help="show capacity and dedup stats")
    q.set_defaults(func=cmd_df)

    q = sub.add_parser("fsck", help="check and heal redundancy")
    q.add_argument("--repair", action="store_true", help="re-replicate degraded chunks")
    q.add_argument("--deep", action="store_true", help="also verify every stored blob's hash")
    q.set_defaults(func=cmd_fsck)

    q = sub.add_parser("sync", help="mirror the encrypted manifest to providers")
    q.add_argument("direction", choices=["push", "pull"])
    q.set_defaults(func=cmd_sync)

    q = sub.add_parser("dashboard", help="write a static HTML status page")
    q.add_argument("-o", "--out", default="starling-dashboard.html")
    q.set_defaults(func=cmd_dashboard)

    q = sub.add_parser("optimize", help="recompress stored data with the best codec")
    q.add_argument("--delta", action="store_true",
                   help="also delta-compress near-duplicate chunks (backups, versions)")
    q.set_defaults(func=cmd_optimize)

    q = sub.add_parser("gc", help="collect orphaned chunks and repair reference counts")
    q.add_argument("--prune", action="store_true",
                   help="also delete provider blobs the manifest no longer references")
    q.set_defaults(func=cmd_gc)

    dic = sub.add_parser("dict", help="manage the shared compression dictionary")
    dsub = dic.add_subparsers(dest="dcmd", required=True)
    dt = dsub.add_parser("train", help="build a shared dictionary to shrink similar files")
    dt.add_argument("paths", nargs="*",
                    help="sample files/dirs to learn from (default: existing vault data)")
    dt.add_argument("--recompress", action="store_true",
                    help="also re-encode existing chunks with the new dictionary")
    dt.set_defaults(func=cmd_dict_train)
    ds = dsub.add_parser("show", help="show the active dictionary")
    ds.set_defaults(func=cmd_dict_show)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (VaultError, NotEnoughProviders) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:  # missing files, provider I/O, network
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
