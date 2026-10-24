#!/bin/sh
# Writes a compressed pg_dump to /backups and deletes dumps older than BACKUP_KEEP_DAYS.
# Runs inside the "backup" service; can also be run by hand:
#   docker compose exec backup /ops/backup.sh
set -eu

STAMP=$(date -u +%Y%m%d-%H%M%S)
FILE="/backups/lime-$STAMP.sql.gz"

# Write to a temp file first so a failed dump never looks like a valid backup.
if pg_dump --host=db --username="$PGUSER" --dbname="$PGDATABASE" --no-owner --clean --if-exists | gzip > "$FILE.partial"; then
    mv "$FILE.partial" "$FILE"
    echo "$(date -u +%FT%TZ) backup written: $FILE ($(du -h "$FILE" | cut -f1))"
else
    rm -f "$FILE.partial"
    echo "$(date -u +%FT%TZ) BACKUP FAILED" >&2
    exit 1
fi

find /backups -name 'lime-*.sql.gz' -mtime +"${BACKUP_KEEP_DAYS:-14}" -delete
