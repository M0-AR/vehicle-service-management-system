"""Auth flow: signup -> login -> me -> refresh rotation -> logout -> password."""

from __future__ import annotations

import secrets
from urllib.parse import urlparse

from httpx import AsyncClient

from app.core.tenancy import RESERVED_SLUGS


def _slug(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(3)}"


async def _signup(client: AsyncClient, slug: str, email: str | None = None):
    return await client.post(
        "/api/v1/public/signup",
        json={
            "name": "Riverside Motors",
            "slug": slug,
            "email": email or f"owner@{slug}.example",
            "password": "correct-horse-battery",
        },
    )


async def test_signup_login_me(client: AsyncClient):
    slug = _slug("auth-a")
    response = await _signup(client, slug)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["slug"] == slug
    assert body["access_token"]
    assert urlparse(body["url"]).hostname.startswith(f"{slug}.")

    # Branding is public and tenant-scoped via routing hint.
    branding = await client.get(
        "/api/v1/public/branding", headers={"X-Tenant-Slug": slug}
    )
    assert branding.status_code == 200
    assert branding.json()["slug"] == slug

    # Slug now taken.
    check = await client.get("/api/v1/public/signup/check", params={"slug": slug})
    assert check.json()["available"] is False

    # Duplicate signup rejected.
    duplicate = await _signup(client, slug)
    assert duplicate.status_code == 409

    # Login works and rotates session.
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": f"owner@{slug}.example", "password": "correct-horse-battery"},
        headers={"X-Tenant-Slug": slug},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.status_code == 200
    me_body = me.json()
    assert me_body["user"]["role"] == "owner"
    assert me_body["entitlements"]["plan"] == "free"
    assert me_body["entitlements"]["features"]["white_label"] is False


async def test_login_wrong_password_and_wrong_workspace(client: AsyncClient):
    slug = _slug("auth-b")
    assert (await _signup(client, slug)).status_code == 201

    bad = await client.post(
        "/api/v1/auth/login",
        json={"email": f"owner@{slug}.example", "password": "wrong-password-123"},
        headers={"X-Tenant-Slug": slug},
    )
    assert bad.status_code == 401

    unknown = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@nowhere.example", "password": "whatever-123"},
        headers={"X-Tenant-Slug": "does-not-exist-xyz"},
    )
    assert unknown.status_code == 404


async def test_cross_tenant_login_rejected(client: AsyncClient):
    slug_a, slug_b = _slug("auth-c"), _slug("auth-d")
    assert (await _signup(client, slug_a)).status_code == 201
    assert (await _signup(client, slug_b)).status_code == 201

    # Owner of B cannot log in on A's workspace.
    cross = await client.post(
        "/api/v1/auth/login",
        json={"email": f"owner@{slug_b}.example", "password": "correct-horse-battery"},
        headers={"X-Tenant-Slug": slug_a},
    )
    assert cross.status_code == 401


async def test_refresh_rotation_and_logout(client: AsyncClient):
    slug = _slug("auth-e")
    assert (await _signup(client, slug)).status_code == 201

    old_cookie = client.cookies.get("vsms_refresh")
    assert old_cookie

    refreshed = await client.post(
        "/api/v1/auth/refresh", headers={"X-Tenant-Slug": slug}
    )
    assert refreshed.status_code == 200
    new_cookie = client.cookies.get("vsms_refresh")
    assert new_cookie and new_cookie != old_cookie

    # Replaying the rotated token must fail.
    replay = await client.post(
        "/api/v1/auth/refresh",
        headers={
            "X-Tenant-Slug": slug,
            "Cookie": f"vsms_refresh={old_cookie}",
        },
    )
    assert replay.status_code == 401

    logout = await client.post("/api/v1/auth/logout", headers={"X-Tenant-Slug": slug})
    assert logout.status_code == 200
    after = await client.post("/api/v1/auth/refresh", headers={"X-Tenant-Slug": slug})
    assert after.status_code == 401


async def test_password_change_invalidates_sessions(client: AsyncClient):
    slug = _slug("auth-f")
    email = f"owner@{slug}.example"
    assert (await _signup(client, slug)).status_code == 201

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-battery"},
        headers={"X-Tenant-Slug": slug},
    )
    token = login.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    wrong = await client.post(
        "/api/v1/auth/password",
        json={"current_password": "not-the-password", "new_password": "even-better-password"},
        headers=auth,
    )
    assert wrong.status_code == 400

    changed = await client.post(
        "/api/v1/auth/password",
        json={"current_password": "correct-horse-battery", "new_password": "even-better-password"},
        headers=auth,
    )
    assert changed.status_code == 200

    old_login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-battery"},
        headers={"X-Tenant-Slug": slug},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "even-better-password"},
        headers={"X-Tenant-Slug": slug},
    )
    assert new_login.status_code == 200


async def test_reserved_slug_rejected(client: AsyncClient):
    reserved = next(iter(RESERVED_SLUGS))
    response = await client.post(
        "/api/v1/public/signup",
        json={
            "name": "Reserved Co",
            "slug": reserved,
            "email": "owner@reserved.example",
            "password": "correct-horse-battery",
        },
    )
    assert response.status_code == 422
