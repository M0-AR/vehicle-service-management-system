"""Test bootstrap: real Postgres, real migrations, real RLS.

Strategy (verified approach): create a throwaway database, run Alembic as the
owner (`postgres`), then point the application at it as `app_user` — the
NOSUPERUSER/NOBYPASSRLS runtime role. RLS guarantees are asserted against the
actual database, not mocks.

Prerequisites: Postgres reachable at TEST_ADMIN_DSN (defaults match the
compose service) with the `app_user` role already provisioned (the compose
init script does this).
"""

from __future__ import annotations

import os
import secrets
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

TEST_ADMIN_DSN = os.environ.get(
    "TEST_ADMIN_DSN", "postgresql://postgres:postgres@localhost:5432/postgres"
)
TEST_HOST = os.environ.get("TEST_PG_HOST", "localhost")
TEST_PORT = os.environ.get("TEST_PG_PORT", "5432")
APP_USER = "app_user"
APP_USER_PASSWORD = os.environ.get("TEST_APP_USER_PASSWORD", "app_password")

_TEST_DB_NAME = f"vsms_test_{secrets.token_hex(4)}"


def _parse_admin_dsn(dsn: str) -> dict:
    from urllib.parse import urlparse

    parsed = urlparse(dsn)
    return {
        "host": parsed.hostname or TEST_HOST,
        "port": parsed.port or int(TEST_PORT),
        "user": parsed.username or "postgres",
        "password": parsed.password or "postgres",
    }


_ADMIN = _parse_admin_dsn(TEST_ADMIN_DSN)

# --- environment must be set before app modules are imported -----------------
# ENV=dev keeps refresh cookies non-Secure so httpx will send them over the
# plain-http ASGI transport used in these tests.
os.environ.setdefault("ENV", "dev")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-0123456789abcdef")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("SIGNUP_ENABLED", "true")
os.environ.setdefault(
    "STORAGE_DIR", os.path.join(tempfile.gettempdir(), "vsms-test-uploads")
)
os.environ.setdefault(
    "MASTER_KEK_B64", "dnNtcy10ZXN0LW1hc3Rlci1rZWstMDEyMzQ1Njc4OSE="
)
os.environ["MIGRATION_DATABASE_URL"] = (
    f"postgresql+asyncpg://{_ADMIN['user']}:{_ADMIN['password']}"
    f"@{_ADMIN['host']}:{_ADMIN['port']}/{_TEST_DB_NAME}"
)
os.environ["DATABASE_URL"] = (
    f"postgresql+asyncpg://{APP_USER}:{APP_USER_PASSWORD}"
    f"@{_ADMIN['host']}:{_ADMIN['port']}/{_TEST_DB_NAME}"
)

import asyncpg  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    import asyncio

    async def setup() -> None:
        conn = await asyncpg.connect(
            host=_ADMIN["host"],
            port=_ADMIN["port"],
            user=_ADMIN["user"],
            password=_ADMIN["password"],
            database="postgres",
        )
        try:
            await conn.execute(f'CREATE DATABASE "{_TEST_DB_NAME}"')
        finally:
            await conn.close()

    async def teardown() -> None:
        conn = await asyncpg.connect(
            host=_ADMIN["host"],
            port=_ADMIN["port"],
            user=_ADMIN["user"],
            password=_ADMIN["password"],
            database="postgres",
        )
        try:
            await conn.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}" WITH (FORCE)')
        finally:
            await conn.close()

    try:
        asyncio.run(setup())
    except Exception as exc:  # noqa: BLE001
        pytest.exit(
            f"Cannot reach Postgres at {_ADMIN['host']}:{_ADMIN['port']} ({exc})."
            " Start it with: docker compose up -d postgres",
            returncode=1,
        )
    _run_migrations()
    yield
    asyncio.run(teardown())


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _dispose_engine(database):
    """All tests share one event loop; dispose pools before the loop closes."""
    yield
    from app.db.session import engine

    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def session():
    from app.db.session import SessionLocal

    async with SessionLocal() as s:
        async with s.begin():
            yield s
