#!/usr/bin/env bash
# Local mirror of .github/workflows/ci.yml: ruff, pytest, and a clean-DB migration.
# There is no GitHub remote yet, so this script is the standing CI proof.
# Requires: a container runtime and a project .venv (see README "Dev quickstart").
#   CI_RUNTIME=podman bash scripts/ci.sh   # if the Docker engine is unavailable
set -euo pipefail
cd "$(dirname "$0")/.."

RUNTIME="${CI_RUNTIME:-docker}"

PYTHON=python
[ -x .venv/Scripts/python.exe ] && PYTHON=.venv/Scripts/python.exe
[ -x .venv/bin/python ] && PYTHON=.venv/bin/python
echo "python: $($PYTHON --version) at $PYTHON  |  runtime: $RUNTIME"

PGPORT="${PGPORT:-5432}"
CONTAINER=qs-ci-pg
cleanup() { "$RUNTIME" rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

echo
echo "== lint (ruff) =="
"$PYTHON" -m ruff check .

echo
echo "== start postgres:16 on 127.0.0.1:${PGPORT} =="
"$RUNTIME" run -d --name "$CONTAINER" -p "127.0.0.1:${PGPORT}:5432" \
  -e POSTGRES_USER=quizscan -e POSTGRES_PASSWORD=quizscan -e POSTGRES_DB=quizscan \
  postgres:16 >/dev/null
for _ in $(seq 1 30); do
  "$RUNTIME" exec "$CONTAINER" pg_isready -U quizscan >/dev/null 2>&1 && break
  sleep 1
done

export SECRET_KEY="ci-secret-key-not-for-production"
export DATABASE_URL="postgres://quizscan:quizscan@127.0.0.1:${PGPORT}/quizscan"

echo
echo "== tests (pytest) =="
"$PYTHON" -m pytest -q

echo
echo "== clean-DB migration (fresh database -> head) =="
docker exec "$CONTAINER" psql -U quizscan -d quizscan -c "DROP DATABASE IF EXISTS ci_fresh;" >/dev/null
docker exec "$CONTAINER" psql -U quizscan -d quizscan -c "CREATE DATABASE ci_fresh;" >/dev/null
FRESH="postgres://quizscan:quizscan@127.0.0.1:${PGPORT}/ci_fresh"
DATABASE_URL="$FRESH" "$PYTHON" manage.py migrate
DATABASE_URL="$FRESH" "$PYTHON" manage.py migrate --check

echo
echo "== backup / restore round-trip (R8.2) =="
# its own disposable container + port, independent of this script's postgres
env -u DATABASE_URL PGPORT=5455 CI_RUNTIME="$RUNTIME" bash scripts/check_backup_restore.sh

echo
echo "ALL GREEN"
