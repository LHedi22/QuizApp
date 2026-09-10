#!/usr/bin/env bash
# Tested restore (REBUILD_SPEC R8.2): seed -> backup -> wipe -> restore, then
# assert the backup-critical state (quizzes, immutable version maps, stored PDF
# bytes) came back byte-for-byte. Self-contained: spins its own postgres:16.
#
#   bash scripts/check_backup_restore.sh
set -euo pipefail
cd "$(dirname "$0")/.."

RUNTIME="${CI_RUNTIME:-docker}"
PGPORT="${PGPORT:-5445}"
CONTAINER=qs-br-pg
DB=quizscan
PYTHON=python
[ -x .venv/Scripts/python.exe ] && PYTHON=.venv/Scripts/python.exe
[ -x .venv/bin/python ] && PYTHON=.venv/bin/python

WORK="$(mktemp -d)"
MEDIA="${WORK}/media"
BK="${WORK}/backups"
mkdir -p "$MEDIA" "$BK"

cleanup() { "$RUNTIME" rm -f "$CONTAINER" >/dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT
cleanup

echo "== start postgres:16 on 127.0.0.1:${PGPORT} =="
"$RUNTIME" run -d --name "$CONTAINER" -p "127.0.0.1:${PGPORT}:5432" \
  -e POSTGRES_USER="$DB" -e POSTGRES_PASSWORD="$DB" -e POSTGRES_DB="$DB" postgres:16 >/dev/null
for _ in $(seq 1 30); do
  "$RUNTIME" exec "$CONTAINER" pg_isready -U "$DB" >/dev/null 2>&1 && break
  sleep 1
done

export DJANGO_SETTINGS_MODULE=app.settings
export SECRET_KEY=br-secret-not-for-production
export DATABASE_URL="postgres://${DB}:${DB}@127.0.0.1:${PGPORT}/${DB}"
export MEDIA_ROOT="$MEDIA"

echo "== seed =="
"$PYTHON" manage.py migrate >/dev/null
"$PYTHON" scripts/seed_demo.py

"$PYTHON" scripts/_br_snapshot.py > "${WORK}/before.txt"
echo "-- snapshot before --"; cat "${WORK}/before.txt"

echo "== backup =="
bash deploy/backup.sh --out "$BK" --pg-container "$CONTAINER" --media-dir "$MEDIA" \
  --db-user "$DB" --db-name "$DB"
TS="$(ls "$BK")"

echo "== wipe =="
"$RUNTIME" exec -i "$CONTAINER" psql -U "$DB" -d postgres \
  -c "DROP DATABASE ${DB} WITH (FORCE);" -c "CREATE DATABASE ${DB};" >/dev/null
"$PYTHON" manage.py migrate >/dev/null           # empty schema so the snapshot can connect
find "$MEDIA" -mindepth 1 -delete
"$PYTHON" scripts/_br_snapshot.py > "${WORK}/wiped.txt"
grep -qx "quiz=0" "${WORK}/wiped.txt" || { echo "FAIL: wipe left data"; exit 1; }

echo "== restore =="
bash deploy/restore.sh --yes "${BK}/${TS}" --pg-container "$CONTAINER" --media-dir "$MEDIA" \
  --db-user "$DB" --db-name "$DB"

"$PYTHON" scripts/_br_snapshot.py > "${WORK}/after.txt"
echo "-- snapshot after --"; cat "${WORK}/after.txt"

if diff -u "${WORK}/before.txt" "${WORK}/after.txt"; then
  echo
  echo "RESTORE VERIFIED"
else
  echo
  echo "FAIL: RESTORE MISMATCH"
  exit 1
fi
