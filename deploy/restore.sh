#!/usr/bin/env bash
# Restore a quizscan backup produced by deploy/backup.sh (REBUILD_SPEC R8.2).
# DESTRUCTIVE: pg_restore --clean drops and recreates objects; the blob extract
# overwrites the store. Requires --yes.
#
# Usage:
#   bash deploy/restore.sh --yes <timestamp|backup-dir>
#   bash deploy/restore.sh --yes <dir> --pg-container NAME --media-dir /path/to/blob
set -euo pipefail
cd "$(dirname "$0")/.."

RUNTIME="${CI_RUNTIME:-docker}"
[ -f deploy/.env ] && set -a && . deploy/.env && set +a

BACKUP_DIR="${BACKUP_DIR:-deploy/backups}"
PG_CONTAINER="${PG_CONTAINER:-quizscan-postgres-1}"
BLOB_VOLUME="${BLOB_VOLUME:-quizscan_blobstore}"
MEDIA_DIR=""
DB_USER="${POSTGRES_USER:-quizscan}"
DB_NAME="${POSTGRES_DB:-quizscan}"
CONFIRMED=0
SRC=""

while [ $# -gt 0 ]; do
  case "$1" in
    --yes) CONFIRMED=1; shift ;;
    --pg-container) PG_CONTAINER="$2"; shift 2 ;;
    --blob-volume) BLOB_VOLUME="$2"; MEDIA_DIR=""; shift 2 ;;
    --media-dir) MEDIA_DIR="$2"; BLOB_VOLUME=""; shift 2 ;;
    --db-user) DB_USER="$2"; shift 2 ;;
    --db-name) DB_NAME="$2"; shift 2 ;;
    -*) echo "restore.sh: unknown arg '$1'" >&2; exit 2 ;;
    *) SRC="$1"; shift ;;
  esac
done

[ -n "$SRC" ] || { echo "restore.sh: give a backup timestamp or directory" >&2; exit 2; }
[ -d "$SRC" ] || SRC="${BACKUP_DIR}/${SRC}"
[ -d "$SRC" ] || { echo "restore.sh: no such backup: $SRC" >&2; exit 2; }
[ -s "${SRC}/db.dump" ] && [ -s "${SRC}/blob.tar.gz" ] || {
  echo "restore.sh: $SRC is missing db.dump / blob.tar.gz" >&2; exit 2; }

if [ "$CONFIRMED" -ne 1 ]; then
  echo "restore.sh: refusing to overwrite $DB_NAME + the blob store without --yes" >&2
  echo "            (source: $SRC)" >&2
  exit 3
fi

echo "restore <- $SRC   (db=$DB_NAME container=$PG_CONTAINER)"

# --- database ----------------------------------------------------------
"$RUNTIME" exec -i "$PG_CONTAINER" pg_restore --clean --if-exists --no-owner --exit-on-error \
  -U "$DB_USER" -d "$DB_NAME" < "${SRC}/db.dump"

# --- blob store ------------------------------------------------------
if [ -n "$MEDIA_DIR" ]; then
  mkdir -p "$MEDIA_DIR"
  find "$MEDIA_DIR" -mindepth 1 -delete
  tar xzf "${SRC}/blob.tar.gz" -C "$MEDIA_DIR"
else
  "$RUNTIME" run --rm -v "${BLOB_VOLUME}:/blob" -v "$(pwd)/${SRC}:/in:ro" \
    alpine sh -c 'find /blob -mindepth 1 -delete && tar xzf /in/blob.tar.gz -C /blob'
fi

# --- schema sanity ---------------------------------------------------
PYTHON=python
[ -x .venv/Scripts/python.exe ] && PYTHON=.venv/Scripts/python.exe
[ -x .venv/bin/python ] && PYTHON=.venv/bin/python
if [ -n "${DATABASE_URL:-}" ]; then
  "$PYTHON" manage.py migrate --check
  echo "schema at head after restore"
else
  echo "(set DATABASE_URL to run 'migrate --check' after restore)"
fi

echo "RESTORE DONE"
