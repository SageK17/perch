#!/usr/bin/env bash
# Starling end-to-end demo: pool 8 "free accounts", store a file with
# erasure coding, lose two providers, recover anyway, then self-heal.
#
#   bash examples/demo.sh
#
# Uses local folders to stand in for real free-tier cloud accounts. The engine
# treats them identically to remote providers.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$HERE"
export STARLING_PASSPHRASE="demo-passphrase-please-change"

WORK="$(mktemp -d)"
export STARLING_VAULT="$WORK/vault"
trap 'rm -rf "$WORK"' EXIT
S() { python3 -m starling "$@"; }

echo "== 1. Create a vault with Reed-Solomon 4+2 (survives 2 lost providers) =="
S init --policy erasure -k 4 -m 2

echo; echo "== 2. Pool 8 'free accounts' (15 GB each = 120 GB pooled) =="
for i in $(seq 1 8); do
  S provider add --id cloud$i --kind local --root "$WORK/clouds/cloud$i" --capacity 15GB >/dev/null
done
S provider ls

echo; echo "== 3. Store a 1.5 MB file, plus an identical copy (watch dedup) =="
head -c 1500000 /dev/urandom > "$WORK/photo.raw"
cp "$WORK/photo.raw" "$WORK/photo-copy.raw"
S put "$WORK/photo.raw"      album/photo.raw
S put "$WORK/photo-copy.raw" album/photo-copy.raw   # 0 new chunks -> deduped

echo; echo "== 4. Vault status =="
S df

echo; echo "== 5. Two providers go dark (delete their data) =="
rm -rf "$WORK/clouds/cloud2"/* "$WORK/clouds/cloud5"/*
echo "wiped cloud2 and cloud5"

echo; echo "== 6. Download anyway — reconstructed from surviving shards =="
S get album/photo.raw "$WORK/restored.raw"
if cmp -s "$WORK/photo.raw" "$WORK/restored.raw"; then
  echo "restored file is byte-for-byte identical despite 2 dead providers ✓"
else
  echo "MISMATCH!"; exit 1
fi

echo; echo "== 7. Self-heal: rebuild the missing shards onto healthy providers =="
S fsck --repair
S fsck   # should now report 0 degraded

echo; echo "== 8. Write a static HTML dashboard =="
S dashboard -o "$WORK/dashboard.html"
echo "dashboard bytes: $(wc -c < "$WORK/dashboard.html")"
echo; echo "Demo complete."
