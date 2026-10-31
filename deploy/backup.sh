#!/usr/bin/env bash
# Daily encrypted backup of the database and uploaded files (spec section 11).
# Run by cron as root:   30 2 * * * /srv/hrweb/app-production/deploy/backup.sh production
# BACKUP_PASSPHRASE_FILE holds the encryption passphrase; keep a copy off the server,
# because backups cannot be restored without it.
# Set BACKUP_RCLONE_REMOTE (for example arvan:hrweb-backups) to copy them to a second place.
set -euo pipefail

APP_ENV="${1:?usage: backup.sh <production|staging>}"
DATA_DIR="/srv/hrweb/$APP_ENV"
ENV_FILE="$DATA_DIR/.env"
KEEP_DAYS="${KEEP_DAYS:-14}"
PASSPHRASE_FILE="${BACKUP_PASSPHRASE_FILE:-/srv/hrweb/backup-passphrase}"
BACKUP_DIR="$DATA_DIR/backups"
STAMP="$(date +%Y%m%d-%H%M)"

[ -s "$PASSPHRASE_FILE" ] || { echo "missing passphrase file: $PASSPHRASE_FILE" >&2; exit 2; }
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

encrypt() {
  openssl enc -aes-256-cbc -pbkdf2 -salt -pass "file:$PASSPHRASE_FILE"
}

DB_FILE="$BACKUP_DIR/db-$STAMP.sql.gz.enc"
docker exec "hrweb-$APP_ENV-db-1" pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip | encrypt >"$DB_FILE"

MEDIA_FILE="$BACKUP_DIR/media-$STAMP.tar.gz.enc"
tar -C "$DATA_DIR" -czf - media | encrypt >"$MEDIA_FILE"

# An empty dump means pg_dump failed silently; fail loudly instead
[ "$(stat -c %s "$DB_FILE")" -gt 1024 ] || { echo "database backup looks empty" >&2; exit 1; }

find "$BACKUP_DIR" -name '*.enc' -mtime +"$KEEP_DAYS" -delete

if [ -n "${BACKUP_RCLONE_REMOTE:-}" ]; then
  rclone copy "$BACKUP_DIR" "$BACKUP_RCLONE_REMOTE/$APP_ENV"
fi
echo "backup done: $DB_FILE"
