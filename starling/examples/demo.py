"""
Using Starling as a library (rather than the CLI).

    python3 examples/demo.py

Pools a handful of local folders (standing in for free cloud accounts), stores
some data with erasure coding, simulates a provider outage, and recovers.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from starling import Policy, Vault


def main() -> None:
    with tempfile.TemporaryDirectory() as work:
        providers = [
            {"id": f"cloud{i}", "kind": "local",
             "root": os.path.join(work, f"cloud{i}"), "capacity": 15 * 10**9}
            for i in range(6)
        ]
        # Erasure code 3+2: survives any 2 providers dying, ~1.67x space.
        vault = Vault.create(os.path.join(work, "vault"), "example-passphrase",
                             policy=Policy(mode="erasure", k=3, m=2),
                             providers=providers)

        payload = b"the quick brown fox " * 5000  # ~100 KB, very compressible
        vault.put_bytes(payload, "notes/fox.txt")
        vault.put_bytes(payload, "notes/fox-copy.txt")  # identical -> deduped

        stats = vault.stats()
        print(f"policy         : {stats['policy']}")
        print(f"files/chunks   : {stats['files']}/{stats['chunks']}")
        print(f"logical        : {stats['logical_bytes']} bytes")
        print(f"stored (phys.) : {stats['stored_bytes']} bytes "
              f"(dedup {stats['dedup_ratio']:.2f}x, "
              f"{stats['space_amplification']:.2f}x amplification)")

        # A provider vanishes.
        gone = "cloud1"
        for key in list(vault.backends[gone].list_keys()):
            vault.backends[gone].delete(key)
        print(f"\nwiped provider {gone}; reading back anyway...")

        assert vault.get_bytes("notes/fox.txt") == payload
        print("recovered the file byte-for-byte from surviving shards ✓")

        healed = vault.fsck(repair=True)
        print(f"fsck --repair: repaired {healed['repaired']} degraded chunk(s)")


if __name__ == "__main__":
    main()
