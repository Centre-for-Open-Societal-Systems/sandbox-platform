#!/bin/sh
# Start-up for the API container:
#   1. wait for PostgreSQL,
#   2. apply Alembic migrations (no-op when the schema is current),
#   3. optionally seed reference data / the master admin (idempotent),
#   4. optionally load the demo catalogue (A2C + OpenG2P; re-runnable),
#   5. hand over to the server command.
set -e

echo "[entrypoint] waiting for the database at ${DB_HOST}:${DB_PORT}..."
python - <<'PY'
import sys
import time

from sqlalchemy import create_engine, text

from app.config.settings import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
for attempt in range(60):
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        print("[entrypoint] database is ready")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 - any failure means "not yet"
        print(f"[entrypoint] database not ready ({exc.__class__.__name__}), retrying...")
        time.sleep(2)
sys.exit("[entrypoint] database did not become ready in 120 s")
PY

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[entrypoint] applying migrations"
  alembic upgrade head
fi

if [ -n "${SEED_ADMIN_PASSWORD}" ]; then
  echo "[entrypoint] seeding reference data (existing rows are kept)"
  python -m app.seeds.seed
fi

if [ "${LOAD_DEMO_CATALOGUE:-false}" = "true" ]; then
  echo "[entrypoint] loading the demo catalogue (A2C + OpenG2P)"
  python scripts/a2c/load_a2c.py
  python scripts/openg2p/load_bene_portal.py
  python scripts/openg2p/bene_portal_samples.py
fi

exec "$@"
