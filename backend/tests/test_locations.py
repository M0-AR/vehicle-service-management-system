"""Tier C multi-location: provisioning, CRUD rules, order assignment, isolation.

Every tenant is provisioned with a default "Main location"; orders take the
default unless a branch is chosen, and the order list can be filtered per
location. Locations are not plan-gated, so a free workspace must be able to add
a second branch.
"""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from test_api_flow import (  # fixtures/helpers reused across test modules
    _create_customer,
    _create_vehicle,
    _headers,
    make_workspace,  # noqa: F401  (pytest fixture)
)


async def _locations(client, auth) -> list[dict]:
    response = await client.get("/api/v1/locations", headers=auth)
    assert response.status_code == 200, response.text
    return response.json()


async def _create_location(client, auth, name: str, **extra) -> dict:
    response = await client.post(
        "/api/v1/locations", json={"name": name, **extra}, headers=auth
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_order(client, auth, vehicle_id: str, **extra) -> dict:
    response = await client.post(
        "/api/v1/service-orders",
        json={
            "vehicle_id": vehicle_id,
            "description": "Location fixture order",
            **extra,
        },
        headers=auth,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_default_location_and_crud_rules(make_workspace):
    client, slug, _email, token = await make_workspace("loccrud")
    auth = _headers(slug, token)

    seeded = await _locations(client, auth)
    assert [item["name"] for item in seeded] == ["Main location"]
    assert seeded[0]["is_default"] is True

    second = await _create_location(client, auth, "North Branch")
    assert second["is_default"] is False

    third = await _create_location(client, auth, "South Branch", is_default=True)
    assert third["is_default"] is True
    by_name = {item["name"]: item for item in await _locations(client, auth)}
    assert by_name["Main location"]["is_default"] is False
    assert by_name["South Branch"]["is_default"] is True

    duplicate = await client.post(
        "/api/v1/locations", json={"name": "north branch"}, headers=auth
    )
    assert duplicate.status_code == 409, duplicate.text

    unset = await client.patch(
        f"/api/v1/locations/{third['id']}", json={"is_default": False}, headers=auth
    )
    assert unset.status_code == 422

    deleted_default = await client.delete(
        f"/api/v1/locations/{third['id']}", headers=auth
    )
    assert deleted_default.status_code == 409

    removed = await client.delete(f"/api/v1/locations/{second['id']}", headers=auth)
    assert removed.status_code == 200 and removed.json()["ok"] is True, removed.text

    restored = await client.patch(
        f"/api/v1/locations/{seeded[0]['id']}", json={"is_default": True}, headers=auth
    )
    assert restored.status_code == 200 and restored.json()["is_default"] is True

    survivor = await client.delete(f"/api/v1/locations/{third['id']}", headers=auth)
    assert survivor.status_code == 200, survivor.text

    last = await client.delete(f"/api/v1/locations/{seeded[0]['id']}", headers=auth)
    assert last.status_code == 409
    assert "at least one location" in last.json()["detail"]


async def test_location_write_roles(make_workspace):
    client, slug, _email, token = await make_workspace("locroles")
    auth = _headers(slug, token)

    staff = await client.post(
        "/api/v1/staff",
        json={
            "email": f"mgr@{slug}.example",
            "name": "Maya Reyes",
            "password": "manager-pass-123",
            "role": "manager",
        },
        headers=auth,
    )
    assert staff.status_code == 201, staff.text

    from app.main import app

    manager_client = AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    )
    try:
        login = await manager_client.post(
            "/api/v1/auth/login",
            json={"email": f"mgr@{slug}.example", "password": "manager-pass-123"},
            headers={"X-Tenant-Slug": slug},
        )
        assert login.status_code == 200, login.text
        manager_auth = _headers(slug, login.json()["access_token"])

        listing = await manager_client.get("/api/v1/locations", headers=manager_auth)
        assert listing.status_code == 200 and len(listing.json()) == 1

        denied = await manager_client.post(
            "/api/v1/locations", json={"name": "Manager Branch"}, headers=manager_auth
        )
        assert denied.status_code == 403, denied.text
    finally:
        await manager_client.aclose()


async def test_orders_take_default_and_filter_by_location(make_workspace):
    client, slug, _email, token = await make_workspace("locorders")
    auth = _headers(slug, token)

    default = (await _locations(client, auth))[0]
    customer = await _create_customer(client, slug, token, name="Layla Haddad")
    vehicle = await _create_vehicle(client, slug, token, customer["id"])

    implied = await _create_order(client, auth, vehicle["id"])
    assert implied["location_id"] == default["id"]

    north = await _create_location(client, auth, "North Branch")
    assigned = await _create_order(client, auth, vehicle["id"], location_id=north["id"])
    assert assigned["location_id"] == north["id"]

    unknown = await client.post(
        "/api/v1/service-orders",
        json={"vehicle_id": vehicle["id"], "description": "Bad location", "location_id": None},
        headers=auth,
    )
    assert unknown.status_code == 201  # None falls back to the default
    assert unknown.json()["location_id"] == default["id"]

    filtered = await client.get(
        f"/api/v1/service-orders?location_id={north['id']}", headers=auth
    )
    assert filtered.status_code == 200, filtered.text
    items = filtered.json()["items"]
    assert filtered.json()["total"] == 1
    assert items[0]["location_name"] == "North Branch"
    assert items[0]["id"] == assigned["id"]

    moved = await client.patch(
        f"/api/v1/service-orders/{assigned['id']}",
        json={"location_id": default["id"]},
        headers=auth,
    )
    assert moved.status_code == 200 and moved.json()["location_id"] == default["id"]

    cleared = await client.patch(
        f"/api/v1/service-orders/{assigned['id']}",
        json={"location_id": None},
        headers=auth,
    )
    assert cleared.status_code == 422

    again = await _create_order(
        client, auth, vehicle["id"], location_id=north["id"]
    )
    in_use = await client.delete(f"/api/v1/locations/{north['id']}", headers=auth)
    assert in_use.status_code == 409 and "history" in in_use.json()["detail"]

    await client.patch(
        f"/api/v1/service-orders/{again['id']}",
        json={"location_id": default["id"]},
        headers=auth,
    )
    empty = await client.get(
        f"/api/v1/service-orders?location_id={north['id']}", headers=auth
    )
    assert empty.status_code == 200 and empty.json()["total"] == 0

    removed = await client.delete(f"/api/v1/locations/{north['id']}", headers=auth)
    assert removed.status_code == 200, removed.text


async def test_locations_are_tenant_isolated(make_workspace):
    client_a, slug_a, _email_a, token_a = await make_workspace("lociso-a")
    client_b, slug_b, _email_b, token_b = await make_workspace("lociso-b")
    auth_a = _headers(slug_a, token_a)
    auth_b = _headers(slug_b, token_b)

    mine = await _create_location(client_a, auth_a, "A Only Branch")
    theirs = await _locations(client_b, auth_b)
    assert [item["name"] for item in theirs] == ["Main location"]

    hidden = await client_b.patch(
        f"/api/v1/locations/{mine['id']}", json={"name": "Stolen"}, headers=auth_b
    )
    assert hidden.status_code == 404
