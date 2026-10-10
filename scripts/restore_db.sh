#!/bin/sh
set -eu

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <backup-file> <target-db-or-database-url>" >&2
  echo "Set ALLOW_RESTORE=1 to confirm destructive restore intent." >&2
  exit 1
fi

BACKUP="$1"
TARGET="$2"

if [ "${ALLOW_RESTORE:-}" != "1" ]; then
  echo "Refusing restore without ALLOW_RESTORE=1." >&2
  exit 1
fi

if [ ! -f "$BACKUP" ]; then
  echo "Backup file not found: $BACKUP" >&2
  exit 1
fi

case "$TARGET" in
  postgresql://*|postgresql+psycopg://*)
    if ! command -v psql >/dev/null 2>&1; then
      echo "psql is required for PostgreSQL restore." >&2
      exit 1
    fi
    PG_URL="$(printf '%s' "$TARGET" | sed 's/^postgresql+psycopg:/postgresql:/')"
    case "$BACKUP" in
      *.gz) gzip -dc "$BACKUP" | psql "$PG_URL" ;;
      *) psql "$PG_URL" < "$BACKUP" ;;
    esac
    printf '%s\n' "$TARGET"
    ;;
  *)
    mkdir -p "$(dirname "$TARGET")"
    python3 - "$BACKUP" "$TARGET" <<'PY'
import sqlite3
import sys

source, target = sys.argv[1:3]
src = sqlite3.connect(source)
dst = sqlite3.connect(target)
try:
    src.backup(dst)
finally:
    dst.close()
    src.close()
print(target)
PY
    ;;
esac
