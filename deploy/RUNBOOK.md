# quizscan — ops runbook

Localhost prototype: one `docker compose` stack (Postgres + app + Django-Q2
worker), no TLS, no reverse proxy, no remote deploy (REBUILD_SPEC §3, §6). Every
command below has been run during Phase 12.

All `docker compose` commands assume you run them from the repo root with:

```
docker compose --env-file deploy/.env -f deploy/docker-compose.yml <...>
```

---

## First run

```
cp deploy/.env.example deploy/.env
# set a real SECRET_KEY:
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64))"   # paste into deploy/.env
# pick free host ports in deploy/.env (defaults APP_PORT=8010, PG_PORT=5432)

docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d --build
```

The `app` container migrates + `collectstatic`s on boot, then serves on
`http://localhost:${APP_PORT}`. The `worker` waits for `app` to be healthy so the
Django-Q2 tables exist before the cluster starts.

Create a login:

```
docker compose … exec app python manage.py createsuperuser
```

(Professors also self-sign-up at `/accounts/register/` — open, localhost only.)

Health check: `curl -fsS http://localhost:${APP_PORT}/healthz` → `{"status": "ok"}`.

---

## Everyday

```
docker compose … ps                 # what's running
docker compose … logs -f app        # follow app logs
docker compose … logs -f worker     # follow the Q2 cluster
docker compose … restart app        # restart just the web process
docker compose … down               # stop (keeps volumes / data)
docker compose … up -d              # start again
```

Data lives in two named volumes: **`quizscan_pgdata`** (Postgres) and
**`quizscan_blobstore`** (generated PDFs and scanned answer-sheet photos —
`submissions/<version_id>/<uuid>.jpg`, Phase 7).
`docker compose … down -v` deletes both — see "Wipe & reseed".

---

## Backup

```
bash deploy/backup.sh
```

Writes `deploy/backups/<UTC-timestamp>/`:

| file | what |
|---|---|
| `db.dump` | `pg_dump -Fc` of the whole database (the `version` shuffle maps are irreplaceable — R2.7/R8.2) |
| `blob.tar.gz` | the entire blob store |
| `manifest.txt` | git SHA, row counts, file sizes |

`deploy/backups/` is gitignored. The script reads container / volume / DB names
from `deploy/.env`; override with `--pg-container`, `--blob-volume` /
`--media-dir`, `--db-user`, `--db-name`, `--out`.

Off-host / scheduled backups are **out of scope** for the prototype. If you want a
nightly local copy anyway, a cron line is roughly:

```
# 0 2 * * *  cd /path/to/quizscanapp && bash deploy/backup.sh >> deploy/backups/cron.log 2>&1
```

(not wired — you add it yourself.)

---

## Restore

**Destructive.** `pg_restore --clean` drops and recreates objects; the blob
extract overwrites the store. Requires `--yes`.

```
bash deploy/restore.sh --yes <timestamp>          # e.g. 20260910T214422Z
# or an explicit dir:
bash deploy/restore.sh --yes deploy/backups/20260910T214422Z
```

After it prints `RESTORE DONE`, verify:

```
docker compose … exec app python manage.py migrate --check      # exit 0 = schema at head
docker compose … exec app python manage.py shell -c \
  "from app.core.models import Quiz, Version; print(Quiz.objects.count(), Version.objects.count())"
```

To prove the whole round-trip end to end (seed → backup → wipe → restore →
byte-for-byte compare) against a disposable database:

```
bash scripts/check_backup_restore.sh        # prints RESTORE VERIFIED
```

---

## Wipe & reseed

Throw away all data and start from a small demo dataset:

```
docker compose … down -v
docker compose … up -d --build
docker compose … exec app python scripts/seed_demo.py
```

`seed_demo.py` creates `demo@example.com` / `demo-pass-12345`, one 12-question
quiz, 3 generated versions, and their PDFs. Re-running it resets that professor
(it does not touch other accounts).

---

## Troubleshooting

- **Port bind fails on Windows** (`bind: An attempt was made to access a socket
  in a way forbidden`) — the port is in a WinNAT-reserved range. Check with
  `netsh interface ipv4 show excludedportrange protocol=tcp` and pick another
  `APP_PORT` / `PG_PORT` in `deploy/.env`. `8000` and `5432` are also commonly
  taken by other dev tooling.
- **Worker logs `relation "django_q_ormq" does not exist`** on first boot — the
  worker started before `app` finished migrating. The compose file already gates
  `worker` on `app: service_healthy`; if you see it, `docker compose … restart
  worker` once and it self-heals.
- **Docker Desktop wedged** (`docker ps` hangs, API 500s) — restart Docker
  Desktop. For CI-style checks without it, `scripts/ci.sh` accepts
  `CI_RUNTIME=podman`.
- **`collectstatic` fails at boot** — `STATIC_ROOT` (`/app/staticfiles`) must be
  writable by `appuser` (the Dockerfile `chown`s it). WhiteNoise then serves
  `/static/...` directly; there is no nginx.
- **Lost password** — no self-service reset (by design, §6 Q13a). Reset via the
  Django admin: `docker compose … exec app python manage.py changepassword <email>`.
