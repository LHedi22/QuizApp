#!/usr/bin/env bash
# Local backup of the quizscan prototype (REBUILD_SPEC R8.2): a pg_dump of the
# database (the `versions` shuffle maps are irreplaceable) plus an archive of the
# blob store (per-version PDFs today, scans once Phase 7 lands).
#
# Writes  <BACKUP_DIR>/<UTC-timestamp>/{db.dump, blob.tar.gz, manifest.txt}
#
# Usage:
#   bash deploy/backup.sh                        # compose stack (deploy/.env)
#   bash deploy/backup.sh --pg-container NAME --blob-volume NAME
#   bash deploy/backup.sh --pg-container NAME --media-dir /path/to/blob   # --local
#
# All Postgres access is via `docker exec` into the named container, so no host
# postgresql-client is required. The blob store is read from a named docker
# volume, or from a host directory with --media-dir.
set -euo pipefail
cd "$(dirname "$0")/.."

# --- config (env / deploy/.env overridable) -------------------------------
[ -f deploy/.env ] && set -a && . deploy/.env && set +a

BACKUP_DIR="${BACKUP_DIR:-deploy/backups}"
PG_CONTAINER="${PG_CONTAINER:-quizscan-postgres-1}"
BLOB_VOLUME="${BLOB_VOLUME:-quizscan_blobstore}"
MEDIA_DIR=""
DB_USER="${POSTGRES_USER:-quizscan}"
DB_NAME="${POSTGRES_DB:-quizscan}"

while [ $# -gt 0 ]; do
  case "$1" in
    --out) BACKUP_DIR="$2"; shift 2 ;;
    --pg-container) PG_CONTAINER="$2"; shift 2 ;;
    --blob-volume) BLOB_VOLUME="$2"; MEDIA_DIR=""; shift 2 ;;
    --media-dir) MEDIA_DIR="$2"; BLOB_VOLUME=""; shift 2 ;;
    --db-user) DB_USER="$2"; shift 2 ;;
    --db-name) DB_NAME="$2"; shift 2 ;;
    *) echo "backup.sh: unknown arg '$1'" >&2; exit 2 ;;
  esac
done

TS="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${BACKUP_DIR}/${TS}"
mkdir -p "$DEST"
echo "backup -> $DEST"

# --- database ------------------------------------------------------------
docker exec -i "$PG_CONTAINER" pg_dump -Fc -U "$DB_USER" -d "$DB_NAME" > "${DEST}/db.dump"
[ -s "${DEST}/db.dump" ] || { echo "backup.sh: db.dump is empty" >&2; exit 1; }

# --- blob store --------------------------------------------------------
if [ -n "$MEDIA_DIR" ]; then
  tar czf "${DEST}/blob.tar.gz" -C "$MEDIA_DIR" .
else
  docker run --rm -v "${BLOB_VOLUME}:/blob:ro" -v "$(pwd)/${DEST}:/out" \
    alpine sh -c 'tar czf /out/blob.tar.gz -C /blob .'
fi
[ -s "${DEST}/blob.tar.gz" ] || { echo "backup.sh: blob.tar.gz is empty" >&2; exit 1; }

# --- manifest --------------------------------------------------------
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
COUNTS="$(docker exec -i "$PG_CONTAINER" psql -tAX -U "$DB_USER" -d "$DB_NAME" -c \
  "select 'quiz='||count(*) from core_quiz
   union all select 'version='||count(*) from core_version
   union all select 'submission='||count(*) from core_submission" | paste -sd' ' -)"
{
  echo "timestamp   $TS"
  echo "git_sha     $GIT_SHA"
  echo "db_dump     $(wc -c < "${DEST}/db.dump") bytes"
  echo "blob_tar    $(wc -c < "${DEST}/blob.tar.gz") bytes"
  echo "row_counts  $COUNTS"
} > "${DEST}/manifest.txt"
cat "${DEST}/manifest.txt"

echo "$DEST"
