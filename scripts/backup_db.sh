#!/bin/sh
set -eu

SOURCE="${1:-${DATABASE_URL:-backend/gluverse.db}}"
BACKUP_DIR="${2:-${BACKUP_DIR:-backups}}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

case "$SOURCE" in
  postgresql://*|postgresql+psycopg://*)
    if ! command -v pg_dump >/dev/null 2>&1; then
      echo "pg_dump is required for PostgreSQL backups." >&2
      exit 1
    fi
    DEST="$BACKUP_DIR/gluverse-postgres-$STAMP.sql.gz"
    if [ -e "$DEST" ]; then
      echo "Backup file already exists: $DEST" >&2
      exit 1
    fi
    PG_URL="$(printf '%s' "$SOURCE" | sed 's/^postgresql+psycopg:/postgresql:/')"
    pg_dump "$PG_URL" | gzip > "$DEST"
    printf '%s\n' "$DEST"
    ;;
  *)
    if [ ! -f "$SOURCE" ]; then
      echo "Source database not found: $SOURCE" >&2
      exit 1
    fi
    BASE="$(basename "$SOURCE")"
    DEST="$BACKUP_DIR/${BASE%.db}-$STAMP.db"
    if [ -e "$DEST" ]; then
      echo "Backup file already exists: $DEST" >&2
      exit 1
    fi
    python3 - "$SOURCE" "$DEST" <<'PY'
import sqlite3
import sys

source, dest = sys.argv[1:3]
src = sqlite3.connect(source)
dst = sqlite3.connect(dest)
try:
    src.backup(dst)
finally:
    dst.close()
    src.close()
print(dest)
PY
    ;;
esac
