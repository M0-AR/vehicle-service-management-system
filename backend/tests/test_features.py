"""Tier A feature flows: pricing catalog, VIN decode, share links, estimates.

Reuses the workspace/customer/vehicle helpers from test_api_flow so the whole
surface is exercised through the real ASGI stack (auth -> RLS -> Postgres).
"""

from __future__ import annotations

from test_api_flow import (  # fixtures/helpers reused across test modules
    _create_customer,
    _create_vehicle,
    _headers,
    make_workspace,  # noqa: F401  (pytest fixture)
)


async def test_public_plans_catalog(client):
    response = await client.get("/api/v1/public/plans")
    assert response.status_code == 200, response.text
    plans = response.json()
    ids = [p["id"] for p in plans]
    assert ids == ["free", "pro", "enterprise"]
    by_id = {p["id"]: p for p in plans}
    assert by_id["free"]["price_monthly_usd"] == 0
    assert by_id["pro"]["price_monthly_usd"] == 29
    assert by_id["enterprise"]["price_monthly_usd"] == 99
    assert "white_label" in by_id["pro"]["features"]
    assert by_id["enterprise"]["limits"]["users"] == -1


async def test_vin_decode_endpoint(make_workspace, monkeypatch):
    client, slug, _email, token = await make_workspace("vin")
    auth = _headers(slug, token)

    bad = await client.get(
        "/api/v1/vehicles/decode-vin", params={"vin": "123"}, headers=auth
    )
    assert bad.status_code == 422

    async def fake_decode(vin: str) -> dict:
        return {
            "vin": vin,
            "decoded": True,
            "make": "HONDA",
            "model": "Civic",
            "year": 2019,
            "trim": "EX",
            "body_class": "Sedan",
            "fuel_type": "petrol",
            "engine": "1.5L I4",
            "vehicle_type": "PASSENGER CAR",
            "message": None,
        }

    monkeypatch.setattr("app.services.vin.decode_vin", fake_decode)
    ok = await client.get(
        "/api/v1/vehicles/decode-vin",
        params={"vin": "19XFC2F69KE201234"},
        headers=auth,
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["decoded"] is True
    assert body["make"] == "HONDA"
    assert body["year"] == 2019
    assert body["fuel_type"] == "petrol"


async def test_order_status_link_flow(make_workspace):
    client, slug, _email, token = await make_workspace("share")
    auth = _headers(slug, token)

    customer = await _create_customer(client, slug, token)
    vehicle = await _create_vehicle(client, slug, token, customer["id"])
    created = await client.post(
        "/api/v1/service-orders",
        json={
            "vehicle_id": vehicle["id"],
            "description": "Timing belt replacement",
            "items": [
                {"kind": "labor", "description": "Belt swap", "quantity": 1, "unit_price": 120}
            ],
        },
        headers=auth,
    )
    assert created.status_code == 201, created.text
    order = created.json()

    shared = await client.post(
        f"/api/v1/service-orders/{order['id']}/share", headers=auth
    )
    assert shared.status_code == 200, shared.text
    link = shared.json()
    assert link["kind"] == "order"
    assert link["url_path"].startswith("/status/")

    # Public payload: no auth, no prices leaked.
    public = await client.get(f"/api/v1/public/orders/{link['token']}")
    assert public.status_code == 200, public.text
    payload = public.json()
    assert payload["number"] == order["number"]
    assert payload["status"] == "scheduled"
    assert payload["vehicle"]["plate_number"] == vehicle["plate_number"]
    assert len(payload["items"]) == 1
    assert set(payload["items"][0].keys()) == {"kind", "description"}
    assert payload["workspace"]["display_name"]

    # Unknown tokens and revoked links behave identically (no oracle).
    unknown = await client.get("/api/v1/public/orders/does-not-exist")
    assert unknown.status_code == 404

    revoked = await client.delete(
        f"/api/v1/service-orders/{order['id']}/share", headers=auth
    )
    assert revoked.status_code == 200
    gone = await client.get(f"/api/v1/public/orders/{link['token']}")
    assert gone.status_code == 404


async def test_estimate_approval_flow(make_workspace):
    client, slug, _email, token = await make_workspace("estim")
    auth = _headers(slug, token)

    customer = await _create_customer(client, slug, token, name="Omar K.")
    vehicle = await _create_vehicle(client, slug, token, customer["id"])

    created = await client.post(
        "/api/v1/estimates",
        json={
            "vehicle_id": vehicle["id"],
            "description": "Brake overhaul",
            "items": [
                {"kind": "labor", "description": "Brake service", "quantity": 1, "unit_price": 60},
                {"kind": "part", "description": "Brake pads", "quantity": 2, "unit_price": 15},
            ],
        },
        headers=auth,
    )
    assert created.status_code == 201, created.text
    estimate = created.json()
    assert estimate["number"].startswith("ES-")
    assert estimate["status"] == "draft"
    assert float(estimate["totals"]["total"]) == 90.0

    # Sending requires at least one item — covered below with an empty one.
    empty = await client.post(
        "/api/v1/estimates",
        json={"vehicle_id": vehicle["id"], "description": "No items yet"},
        headers=auth,
    )
    empty_estimate = empty.json()
    blocked = await client.post(
        f"/api/v1/estimates/{empty_estimate['id']}/send", headers=auth
    )
    assert blocked.status_code == 409

    # No public link before send.
    early = await client.get("/api/v1/public/estimates/anything")
    assert early.status_code == 404

    sent = await client.post(
        f"/api/v1/estimates/{estimate['id']}/send", headers=auth
    )
    assert sent.status_code == 200, sent.text
    link = sent.json()
    assert link["url_path"].startswith("/estimate/")

    staff_view = await client.get(
        f"/api/v1/estimates/{estimate['id']}", headers=auth
    )
    assert staff_view.json()["status"] == "sent"
    assert staff_view.json()["sent_at"] is not None

    public = await client.get(f"/api/v1/public/estimates/{link['token']}")
    assert public.status_code == 200, public.text
    public_payload = public.json()
    assert float(public_payload["totals"]["total"]) == 90.0
    assert len(public_payload["items"]) == 2
    assert public_payload["status"] == "sent"

    approved = await client.post(
        f"/api/v1/public/estimates/{link['token']}/respond",
        json={"decision": "approve", "name": "Omar K."},
    )
    assert approved.status_code == 200, approved.text
    approved_payload = approved.json()
    assert approved_payload["status"] == "approved"
    assert approved_payload["responded_by_name"] == "Omar K."
    assert approved_payload["converted_order_number"].startswith("SO-")

    # Double-response is rejected (atomic claim).
    again = await client.post(
        f"/api/v1/public/estimates/{link['token']}/respond",
        json={"decision": "decline"},
    )
    assert again.status_code == 409

    # The approval created the service order with copied items.
    orders = await client.get("/api/v1/service-orders", headers=auth)
    assert orders.json()["total"] == 1
    order_id = orders.json()["items"][0]["id"]
    order = await client.get(f"/api/v1/service-orders/{order_id}", headers=auth)
    order_body = order.json()
    assert order_body["status"] == "scheduled"
    assert len(order_body["items"]) == 2
    assert estimate["number"] in (order_body["notes"] or "")

    staff_after = await client.get(
        f"/api/v1/estimates/{estimate['id']}", headers=auth
    )
    assert staff_after.json()["converted_order_id"] == order_id

    # Decline path on a second estimate — no order is created.
    second = await client.post(
        "/api/v1/estimates",
        json={
            "vehicle_id": vehicle["id"],
            "description": "Wheel alignment",
            "items": [
                {"kind": "labor", "description": "Alignment", "quantity": 1, "unit_price": 40}
            ],
        },
        headers=auth,
    )
    second_estimate = second.json()
    second_link = (
        await client.post(f"/api/v1/estimates/{second_estimate['id']}/send", headers=auth)
    ).json()
    declined = await client.post(
        f"/api/v1/public/estimates/{second_link['token']}/respond",
        json={"decision": "decline"},
    )
    assert declined.status_code == 200
    assert declined.json()["status"] == "declined"
    assert declined.json()["converted_order_number"] is None

    revoked = await client.delete(
        f"/api/v1/estimates/{second_estimate['id']}/share", headers=auth
    )
    assert revoked.status_code == 200
    gone = await client.get(f"/api/v1/public/estimates/{second_link['token']}")
    assert gone.status_code == 404

    orders_after = await client.get("/api/v1/service-orders", headers=auth)
    assert orders_after.json()["total"] == 1


async def test_estimates_tenant_isolation(make_workspace):
    client_a, slug_a, _email_a, token_a = await make_workspace("est-a")
    client_b, slug_b, _email_b, token_b = await make_workspace("est-b")

    customer = await _create_customer(client_a, slug_a, token_a)
    vehicle = await _create_vehicle(client_a, slug_a, token_a, customer["id"])
    estimate = (
        await client_a.post(
            "/api/v1/estimates",
            json={"vehicle_id": vehicle["id"], "description": "Cross-tenant probe"},
            headers=_headers(slug_a, token_a),
        )
    ).json()

    # B cannot read A's estimate.
    denied = await client_b.get(
        f"/api/v1/estimates/{estimate['id']}", headers=_headers(slug_b, token_b)
    )
    assert denied.status_code == 404

    # B cannot create an estimate against A's vehicle.
    cross = await client_b.post(
        "/api/v1/estimates",
        json={"vehicle_id": vehicle["id"], "description": "Smuggled estimate"},
        headers=_headers(slug_b, token_b),
    )
    assert cross.status_code == 422

    listing = await client_b.get("/api/v1/estimates", headers=_headers(slug_b, token_b))
    assert listing.json()["total"] == 0
