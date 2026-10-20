#!/bin/sh
set -e

echo "[start] waiting for database..."
python - <<'PY'
import asyncio, os, sys
import asyncpg

url = os.environ["MIGRATION_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")

async def main():
    for attempt in range(60):
        try:
            conn = await asyncpg.connect(url)
            await conn.close()
            print("[start] database is up")
            return
        except Exception as exc:
            print(f"[start] db not ready ({attempt}): {exc}")
            await asyncio.sleep(2)
    sys.exit("database never became ready")

asyncio.run(main())
PY

echo "[start] running migrations..."
alembic upgrade head

echo "[start] starting api..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips "*"
