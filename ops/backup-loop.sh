#!/bin/sh
# Entry point of the "backup" service: one backup at start-up, then one every 24 hours.
# (A loop instead of cron because cron jobs don't inherit the container's environment.)
while true; do
    /ops/backup.sh || echo "Backup failed; retrying in 24h" >&2
    sleep 86400
done
