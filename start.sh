#!/bin/sh
# If DATABASE_PATH is set but the file doesn't exist, copy the pre-seeded DB
if [ -n "$DATABASE_PATH" ] && [ ! -f "$DATABASE_PATH" ]; then
    echo "[INIT] No database found at $DATABASE_PATH — copying pre-seeded database..."
    cp /app/maturity.db "$DATABASE_PATH"
    echo "[INIT] Database copied."
fi

exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
