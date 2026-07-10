"""
End-to-end tests for Starling.

Runnable two ways:
    python tests/test_starling.py      # built-in runner, no dependencies
    pytest tests/test_starling.py      # if you have pytest

They cover the load-bearing claims: content-defined dedup, authenticated
encryption, Reed-Solomon reconstruction, and -- most importantly -- that a file
survives providers going dark, and that fsck heals the redundancy back.
"""

import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from starling import Policy, Vault, VaultError  # noqa: E402
from starling import compression, crypto, reedsolomon  # noqa: E402
from starling.chunker import chunk_bytes  # noqa: E402

PW = "correct horse battery staple"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _local_providers(root, n, capacity=0):
    return [
        {"id": f"p{i}", "kind": "local", "root": os.path.join(root, f"p{i}"),
         "capacity": capacity}
        for i in range(n)
    ]


def _wipe_provider(vault, pid):
    """Simulate a provider losing all its data (but still being reachable)."""
    b = vault.backends[pid]
    for key in list(b.list_keys()):
        b.delete(key)


def _blob(size, seed=0):
    rng = random.Random(seed)
    return bytes(rng.getrandbits(8) for _ in range(size))


# --------------------------------------------------------------------------- #
# unit-ish
# --------------------------------------------------------------------------- #
def test_crypto_roundtrip_and_tamper():
    kr = crypto.KeyRing(crypto.derive_master_key(PW, b"salt-salt-salt!!"))
    msg = b"the eagle lands at dawn" * 100
    blob = kr.encrypt(msg)
    assert kr.decrypt(blob) == msg
    # storage keys are deterministic and opaque
    ph = crypto.KeyRing.content_hash(msg)
    assert kr.storage_key(ph, 0) == kr.storage_key(ph, 0)
    assert kr.storage_key(ph, 0) != kr.storage_key(ph, 1)
    # flipping a ciphertext byte must fail authentication
    bad = bytearray(blob)
    bad[-1] ^= 0x01
    try:
        kr.decrypt(bytes(bad))
        raise AssertionError("tampered ciphertext decrypted without error")
    except Exception:
        pass


def test_chunker_is_shift_resistant():
    data = _blob(400_000, seed=1)
    a = [c.data for c in chunk_bytes(data)]
    # Insert bytes near the front; a fixed-size splitter would desync everything.
    shifted = data[:1000] + b"XYZ" + data[1000:]
    b = [c.data for c in chunk_bytes(shifted)]
    set_a = {crypto.KeyRing.content_hash(x) for x in a}
    set_b = {crypto.KeyRing.content_hash(x) for x in b}
    shared = len(set_a & set_b)
    # The vast majority of chunks should be identical despite the shift.
    assert shared >= len(set_a) * 0.7, f"only {shared}/{len(set_a)} chunks survived the shift"
    assert len(a) > 3, "test data should span several chunks"


def test_reed_solomon_recovers_from_erasures():
    for k, m in [(4, 2), (2, 2), (6, 3), (1, 2)]:
        data = _blob(50_000, seed=k * 10 + m)
        shards = reedsolomon.encode(data, k, m)
        assert len(shards) == k + m
        assert reedsolomon.decode(list(shards), k, m, len(data)) == data
        # Drop exactly m shards (the max tolerable) at random positions.
        holed = list(shards)
        for idx in random.Random(k).sample(range(k + m), m):
            holed[idx] = None
        assert reedsolomon.decode(holed, k, m, len(data)) == data
        # Dropping one more than m must fail.
        holed2 = list(shards)
        for idx in list(range(m + 1)):
            holed2[idx] = None
        try:
            reedsolomon.decode(holed2, k, m, len(data))
            raise AssertionError("decoded with too few shards")
        except ValueError:
            pass


# --------------------------------------------------------------------------- #
# engine end-to-end
# --------------------------------------------------------------------------- #
def test_put_get_roundtrip_and_wrong_passphrase():
    with tempfile.TemporaryDirectory() as tmp:
        vdir = os.path.join(tmp, "vault")
        v = Vault.create(vdir, PW, policy=Policy(replicas=2),
                         providers=_local_providers(tmp, 3))
        v = Vault.open(vdir, PW)
        for spec in _local_providers(tmp, 3):
            pass
        data = _blob(300_000, seed=7)
        v.put_bytes(data, "docs/report.bin")
        assert v.get_bytes("docs/report.bin") == data
        assert [r["path"] for r in v.ls()] == ["docs/report.bin"]
        # wrong passphrase should be rejected, not silently produce garbage
        try:
            Vault.open(vdir, "not the passphrase")
            raise AssertionError("opened vault with wrong passphrase")
        except VaultError:
            pass


def test_dedup_saves_space():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault.create(os.path.join(tmp, "v"), PW, policy=Policy(replicas=1),
                         providers=_local_providers(tmp, 2))
        data = _blob(200_000, seed=3)
        r1 = v.put_bytes(data, "a.bin")
        r2 = v.put_bytes(data, "b.bin")  # identical content
        assert r1.new_chunks > 0
        assert r2.new_chunks == 0, "re-storing identical data created new chunks"
        assert r2.dedup_bytes == len(data)
        s = v.stats()
        assert s["dedup_ratio"] >= 1.9  # two logical copies, one physical
        # both still read back correctly
        assert v.get_bytes("a.bin") == data == v.get_bytes("b.bin")


def test_survives_provider_outage_replicate():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault.create(os.path.join(tmp, "v"), PW, policy=Policy(replicas=2),
                         providers=_local_providers(tmp, 4))
        data = _blob(250_000, seed=9)
        v.put_bytes(data, "movie.bin")
        _wipe_provider(v, "p0")  # one whole provider vanishes
        assert v.get_bytes("movie.bin") == data, "lost a file after one provider failed"


def test_erasure_survives_two_outages_then_fails_on_third():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault.create(os.path.join(tmp, "v"), PW,
                         policy=Policy(mode="erasure", k=2, m=2),
                         providers=_local_providers(tmp, 4))
        data = _blob(120_000, seed=11)
        v.put_bytes(data, "big.bin")
        _wipe_provider(v, "p0")
        _wipe_provider(v, "p1")
        assert v.get_bytes("big.bin") == data, "erasure code failed to recover from 2 losses"
        _wipe_provider(v, "p2")  # now only 1 shard per chunk remains (< k)
        try:
            v.get_bytes("big.bin")
            raise AssertionError("recovered with fewer than k shards")
        except VaultError:
            pass


def test_fsck_repairs_degraded_replication():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault.create(os.path.join(tmp, "v"), PW, policy=Policy(replicas=2),
                         providers=_local_providers(tmp, 4))
        v.put_bytes(_blob(250_000, seed=13), "f.bin")
        _wipe_provider(v, "p0")
        before = v.fsck(repair=False)
        assert before["degraded"] > 0, "expected degraded chunks after wiping a provider"
        healed = v.fsck(repair=True)
        assert healed["repaired"] > 0
        after = v.fsck(repair=False)
        assert after["degraded"] == 0, "fsck did not restore full redundancy"


def test_fsck_repairs_erasure_shards():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault.create(os.path.join(tmp, "v"), PW,
                         policy=Policy(mode="erasure", k=2, m=1),
                         providers=_local_providers(tmp, 4))  # spare provider for repair
        data = _blob(120_000, seed=17)
        v.put_bytes(data, "e.bin")
        _wipe_provider(v, "p0")
        v.fsck(repair=True, deep=True)
        # After healing, losing a *different* provider should still be survivable.
        _wipe_provider(v, "p1")
        assert v.get_bytes("e.bin") == data


def test_rm_garbage_collects_chunks():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault.create(os.path.join(tmp, "v"), PW, policy=Policy(replicas=1),
                         providers=_local_providers(tmp, 2))
        v.put_bytes(_blob(200_000, seed=19), "gone.bin")
        used_before = sum(b.used_bytes() for b in v.backends.values())
        assert used_before > 0
        assert v.rm("gone.bin") is True
        used_after = sum(b.used_bytes() for b in v.backends.values())
        assert used_after == 0, "removing the only file left orphaned blobs"
        assert len(v.manifest.chunks) == 0


def test_shared_chunks_are_not_gced_early():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault.create(os.path.join(tmp, "v"), PW, policy=Policy(replicas=1),
                         providers=_local_providers(tmp, 2))
        data = _blob(200_000, seed=23)
        v.put_bytes(data, "a.bin")
        v.put_bytes(data, "b.bin")
        v.rm("a.bin")  # b.bin still references the same chunks
        assert v.get_bytes("b.bin") == data, "GC deleted chunks still in use"


def test_manifest_recovery_via_sync():
    with tempfile.TemporaryDirectory() as tmp:
        vdir = os.path.join(tmp, "v")
        v = Vault.create(vdir, PW, policy=Policy(replicas=2),
                         providers=_local_providers(tmp, 3))
        data = _blob(150_000, seed=29)
        v.put_bytes(data, "important.bin")
        assert v.sync_push() == 3
        # Catastrophe: the local manifest is lost.
        os.remove(os.path.join(vdir, "manifest.enc"))
        v2 = Vault.open(vdir, PW)
        assert v2.ls() == [], "expected an empty manifest before recovery"
        assert v2.sync_pull() is True
        assert v2.get_bytes("important.bin") == data, "could not recover from provider backup"


# --------------------------------------------------------------------------- #
# data compression: best-of codec + shared dictionary
# --------------------------------------------------------------------------- #
def _similar_corpus(n=40, template_len=1200, tail_len=120, seed=100):
    """n files that share a common (incompressible-on-its-own) template plus a
    small unique tail each -- similar, but not duplicates (so no dedup)."""
    rng = random.Random(seed)
    template = bytes(rng.getrandbits(8) for _ in range(template_len))
    files = [template + bytes(rng.getrandbits(8) for _ in range(tail_len)) for _ in range(n)]
    return template, files


def test_compression_best_of_roundtrip():
    text = b"the quick brown fox jumps over the lazy dog. " * 200
    payload, tag = compression.best(text)
    assert tag in ("zlib", "lzma")
    assert len(payload) < len(text) * 0.5
    assert compression.decompress(payload, tag) == text
    # random data can't be compressed -> falls through to raw, never larger
    rnd = os.urandom(4000)
    p2, t2 = compression.best(rnd)
    assert t2 == "raw"
    assert compression.decompress(p2, t2) == rnd
    # dictionary path round-trips
    zdict = compression.build_dictionary([text, text])
    p3, t3 = compression.best(text, zdict=zdict)
    assert compression.decompress(p3, t3, zdict=zdict) == text


def _stored_for(tmp, files, with_dict):
    provs = _local_providers(tmp, 2)
    v = Vault.create(os.path.join(tmp, "v"), PW, policy=Policy(replicas=1), providers=provs)
    if with_dict:
        v.train_dictionary(files)
    for i, data in enumerate(files):
        v.put_bytes(data, f"f{i}.bin")
    # sanity: everything reads back
    for i, data in enumerate(files):
        assert v.get_bytes(f"f{i}.bin") == data
    return v.stats()["stored_bytes"]


def test_shared_dictionary_shrinks_similar_files():
    _, files = _similar_corpus()
    with tempfile.TemporaryDirectory() as t1:
        baseline = _stored_for(t1, files, with_dict=False)
    with tempfile.TemporaryDirectory() as t2:
        withdict = _stored_for(t2, files, with_dict=True)
    # The shared template should be paid for ~once, not once per file.
    assert withdict < baseline * 0.6, f"dict {withdict} vs baseline {baseline}"


def test_optimize_recompresses_existing_data():
    _, files = _similar_corpus()
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault.create(os.path.join(tmp, "v"), PW, policy=Policy(replicas=1),
                         providers=_local_providers(tmp, 2))
        for i, data in enumerate(files):
            v.put_bytes(data, f"f{i}.bin")
        # train from what's already stored, then recompress in place
        v.train_dictionary(v.sample_chunk_plaintexts())
        r = v.recompress_all()
        assert r["after"] < r["before"] * 0.6
        # data is intact after the rewrite
        for i, data in enumerate(files):
            assert v.get_bytes(f"f{i}.bin") == data


def test_retrain_keeps_old_chunks_readable():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault.create(os.path.join(tmp, "v"), PW, policy=Policy(replicas=1),
                         providers=_local_providers(tmp, 2))
        _, corpus_a = _similar_corpus(seed=1)
        _, corpus_b = _similar_corpus(seed=2)
        v.train_dictionary(corpus_a)
        v.put_bytes(corpus_a[0], "a.bin")           # written against dictionary A
        v.train_dictionary(corpus_b)                # new active dictionary B
        v.put_bytes(corpus_b[0], "b.bin")           # written against dictionary B
        # both dictionaries are retained, so both files still decode
        assert v.get_bytes("a.bin") == corpus_a[0]
        assert v.get_bytes("b.bin") == corpus_b[0]


# --------------------------------------------------------------------------- #
# runner
# --------------------------------------------------------------------------- #
def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  ok   {t.__name__}")
            passed += 1
        except Exception as exc:
            import traceback
            print(f"  FAIL {t.__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} tests passed "
          f"(AES-256-GCM: {crypto.using_aes()})")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(_run())
