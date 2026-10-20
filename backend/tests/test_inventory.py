"""Tier C inventory: catalogue, stock ledger, and order line-item draws.

Runs against the real ASGI stack (auth -> RLS -> Postgres), same harness as
the other tier suites.
"""

from __future__ import annotations

from test_api_flow import (  # fixtures/helpers reused across test modules
    _create_customer,
    _create_vehicle,
    _headers,
    make_workspace,  # noqa: F401  (pytest fixture)
)


async def _upgrade_to_pro(client, auth) -> None:
    response = await client.post(
        "/api/v1/settings/billing/checkout", json={"plan": "pro"}, headers=auth
    )
    assert response.status_code == 200, response.text


async def _create_part(client, auth, **overrides) -> dict:
    payload = {
        "name": "Ceramic brake pad set",
        "sku": "BP-100",
        "category": "Brakes",
        "cost": 40,
        "price": 89.5,
        "stock_qty": 10,
        "reorder_level": 3,
    }
    payload.update(overrides)
    response = await client.post("/api/v1/inventory/parts", json=payload, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


async def _draft_order(client, slug, token, auth) -> dict:
    customer = await _create_customer(client, slug, token)
    vehicle = await _create_vehicle(client, slug, token, customer["id"])
    response = await client.post(
        "/api/v1/service-orders",
        json={"vehicle_id": vehicle["id"], "description": "Brake job"},
        headers=auth,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_inventory_is_pro_gated(make_workspace):
    client, slug, _email, token = await make_workspace("gateinv")
    auth = _headers(slug, token)

    response = await client.get("/api/v1/inventory/parts", headers=auth)
    assert response.status_code == 402, response.text

    order = await _draft_order(client, slug, token, auth)
    response = await client.post(
        f"/api/v1/service-orders/{order['id']}/items",
        json={"kind": "part", "part_id": "00000000-0000-0000-0000-000000000001"},
        headers=auth,
    )
    assert response.status_code == 402, response.text


async def test_part_lifecycle_and_stock_ledger(make_workspace):
    client, slug, _email, token = await make_workspace("invlife")
    auth = _headers(slug, token)
    await _upgrade_to_pro(client, auth)

    part = await _create_part(client, auth)
    assert part["sku"] == "BP-100"
    assert float(part["stock_qty"]) == 10

    movements = await client.get(
        f"/api/v1/inventory/movements?part_id={part['id']}", headers=auth
    )
    assert movements.status_code == 200, movements.text
    rows = movements.json()["items"]
    assert len(rows) == 1
    assert rows[0]["reason"] == "received"
    assert float(rows[0]["delta"]) == 10

    adjusted = await client.post(
        f"/api/v1/inventory/parts/{part['id']}/adjust",
        json={"delta": -2, "reason": "adjustment", "note": "Damaged in transit"},
        headers=auth,
    )
    assert adjusted.status_code == 200, adjusted.text
    assert float(adjusted.json()["stock_qty"]) == 8

    overdraw = await client.post(
        f"/api/v1/inventory/parts/{part['id']}/adjust",
        json={"delta": -99, "reason": "adjustment"},
        headers=auth,
    )
    assert overdraw.status_code == 409, overdraw.text

    summary = await client.get("/api/v1/inventory/summary", headers=auth)
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["parts"] == 1
    assert body["low_stock"] == 0
    assert float(body["stock_value"]) == 320.0  # 8 * 40 cost

    low = await client.patch(
        f"/api/v1/inventory/parts/{part['id']}",
        json={"reorder_level": 10},
        headers=auth,
    )
    assert low.status_code == 200, low.text
    summary = await client.get("/api/v1/inventory/summary", headers=auth)
    assert summary.json()["low_stock"] == 1
    filtered = await client.get("/api/v1/inventory/parts?low_stock=true", headers=auth)
    assert [p["id"] for p in filtered.json()["items"]] == [part["id"]]

    search = await client.get("/api/v1/inventory/parts?q=brake", headers=auth)
    assert search.json()["total"] == 1

    archived = await client.delete(f"/api/v1/inventory/parts/{part['id']}", headers=auth)
    assert archived.status_code == 200, archived.text
    listed = await client.get("/api/v1/inventory/parts", headers=auth)
    assert listed.json()["total"] == 0
    everything = await client.get(
        "/api/v1/inventory/parts?include_inactive=true", headers=auth
    )
    assert everything.json()["total"] == 1


async def test_order_items_draw_and_return_stock(make_workspace):
    client, slug, _email, token = await make_workspace("invorder")
    auth = _headers(slug, token)
    await _upgrade_to_pro(client, auth)

    part = await _create_part(client, auth, stock_qty=5)
    order = await _draft_order(client, slug, token, auth)

    added = await client.post(
        f"/api/v1/service-orders/{order['id']}/items",
        json={"kind": "part", "part_id": part["id"], "quantity": 2},
        headers=auth,
    )
    assert added.status_code == 201, added.text
    body = added.json()
    item = body["items"][0]
    assert item["part_id"] == part["id"]
    assert item["description"] == "Ceramic brake pad set"
    assert float(item["unit_price"]) == 89.5

    after = await client.get(f"/api/v1/inventory/parts?q=BP-100", headers=auth)
    assert float(after.json()["items"][0]["stock_qty"]) == 3

    short = await client.post(
        f"/api/v1/service-orders/{order['id']}/items",
        json={"kind": "part", "part_id": part["id"], "quantity": 4},
        headers=auth,
    )
    assert short.status_code == 409, short.text

    removed = await client.delete(
        f"/api/v1/service-orders/{order['id']}/items/{item['id']}", headers=auth
    )
    assert removed.status_code == 200, removed.text
    restored = await client.get("/api/v1/inventory/parts?q=BP-100", headers=auth)
    assert float(restored.json()["items"][0]["stock_qty"]) == 5

    added_again = await client.post(
        f"/api/v1/service-orders/{order['id']}/items",
        json={"kind": "part", "part_id": part["id"], "quantity": 3},
        headers=auth,
    )
    assert added_again.status_code == 201, added_again.text

    cancelled = await client.post(
        f"/api/v1/service-orders/{order['id']}/status",
        json={"status": "cancelled"},
        headers=auth,
    )
    assert cancelled.status_code == 200, cancelled.text
    after_cancel = await client.get("/api/v1/inventory/parts?q=BP-100", headers=auth)
    assert float(after_cancel.json()["items"][0]["stock_qty"]) == 5

    movements = await client.get(
        f"/api/v1/inventory/movements?part_id={part['id']}", headers=auth
    )
    reasons = [m["reason"] for m in movements.json()["items"]]
    assert reasons == ["returned", "issued", "returned", "issued", "received"]


async def test_inventory_is_tenant_isolated(make_workspace):
    client_a, slug_a, _e1, token_a = await make_workspace("inva")
    client_b, slug_b, _e2, token_b = await make_workspace("invb")
    auth_a = _headers(slug_a, token_a)
    auth_b = _headers(slug_b, token_b)
    await _upgrade_to_pro(client_a, auth_a)
    await _upgrade_to_pro(client_b, auth_b)

    part = await _create_part(client_a, auth_a)

    listed_b = await client_b.get("/api/v1/inventory/parts", headers=auth_b)
    assert listed_b.status_code == 200
    assert listed_b.json()["total"] == 0

    foreign = await client_b.post(
        f"/api/v1/inventory/parts/{part['id']}/adjust",
        json={"delta": 1, "reason": "adjustment"},
        headers=auth_b,
    )
    assert foreign.status_code == 404, foreign.text
