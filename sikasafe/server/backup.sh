#!/usr/bin/env bash
# Consistent online backup of the SikaSafe SQLite database.
#
# Safe to run while the server is live (SQLite `.backup` is atomic and WAL-aware).
# Keeps the 30 most recent compressed snapshots.
#
#   ./backup.sh                         # backs up $SIKA_DB (or sikasafe.db) to ./backups
#   ./backup.sh /data/sikasafe.db /data/backups
#   # cron (daily 02:00): 0 2 * * * /app/backup.sh /data/sikasafe.db /data/backups
set -euo pipefail

DB="${1:-${SIKA_DB:-sikasafe.db}}"
DEST="${2:-./backups}"

if [ ! -f "$DB" ]; then
  echo "backup: database not found: $DB" >&2
  exit 1
fi

mkdir -p "$DEST"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$DEST/sikasafe-$STAMP.db"

sqlite3 "$DB" ".backup '$OUT'"
gzip -f "$OUT"

# Retain the 30 newest snapshots.
ls -1t "$DEST"/sikasafe-*.db.gz 2>/dev/null | tail -n +31 | xargs -r rm -f

echo "backup -> $OUT.gz"
