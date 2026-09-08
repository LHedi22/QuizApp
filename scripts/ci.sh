#!/usr/bin/env bash
# Local mirror of .github/workflows/ci.yml: ruff, pytest, and a clean-DB migration.
# There is no GitHub remote yet, so this script is the standing CI proof.
# Requires: docker, and a project .venv (see README "Dev quickstart").
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON=python
[ -x .venv/Scripts/python.exe ] && PYTHON=.venv/Scripts/python.exe
[ -x .venv/bin/python ] && PYTHON=.venv/bin/python
echo "python: $($PYTHON --version) at $PYTHON"

PGPORT="${PGPORT:-5432}"
CONTAINER=qs-ci-pg
cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

echo
echo "== lint (ruff) =="
"$PYTHON" -m ruff check .

echo
echo "== start postgres:16 on 127.0.0.1:${PGPORT} =="
docker run --rm -d --name "$CONTAINER" -p "127.0.0.1:${PGPORT}:5432" \
  -e POSTGRES_USER=quizscan -e POSTGRES_PASSWORD=quizscan -e POSTGRES_DB=quizscan \
  postgres:16 >/dev/null
for _ in $(seq 1 30); do
  docker exec "$CONTAINER" pg_isready -U quizscan >/dev/null 2>&1 && break
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
echo "ALL GREEN"
