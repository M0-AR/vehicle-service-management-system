"""End-to-end API flows and cross-tenant isolation through the whole stack.

Every request goes through the real ASGI app: middleware -> auth deps ->
transaction-scoped RLS context -> Postgres policies as `app_user`.
"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import ASGITransport, AsyncClient


def _slug(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(3)}"


@pytest_asyncio.fixture
async def make_workspace():
    from app.main import app

    clients: list[AsyncClient] = []

    async def _make(prefix: str):
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
        clients.append(client)
        slug = _slug(prefix)
        email = f"owner@{slug}.example"
        response = await client.post(
            "/api/v1/public/signup",
            json={
                "name": f"Workspace {slug}",
                "slug": slug,
                "email": email,
                "password": "correct-horse-battery",
            },
        )
        assert response.status_code == 201, response.text
        token = response.json()["access_token"]
        return client, slug, email, token

    yield _make

    for client in clients:
        await client.aclose()


def _headers(slug: str, token: str) -> dict:
    return {"X-Tenant-Slug": slug, "Authorization": f"Bearer {token}"}


async def _create_customer(client, slug, token, name="Sara Haddad"):
    response = await client.post(
        "/api/v1/customers",
        json={"name": name, "phone": "+1-555-0101"},
        headers=_headers(slug, token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_vehicle(client, slug, token, customer_id):
    response = await client.post(
        "/api/v1/vehicles",
        json={
            "plate_number": f"T{secrets.token_hex(2).upper()}",
            "make": "Toyota",
            "model": "Corolla",
            "year": 2020,
            "fuel_type": "petrol",
            "mileage": 55000,
            "customer_id": customer_id,
        },
        headers=_headers(slug, token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_full_order_to_invoice_lifecycle(make_workspace):
    client, slug, _email, token = await make_workspace("flow")
    auth = _headers(slug, token)

    customer = await _create_customer(client, slug, token)
    vehicle = await _create_vehicle(client, slug, token, customer["id"])

    created = await client.post(
        "/api/v1/service-orders",
        json={
            "vehicle_id": vehicle["id"],
            "description": "Full service",
            "priority": "high",
            "odometer": 55000,
            "items": [
                {"kind": "labor", "description": "Diagnostics", "quantity": 1, "unit_price": 60},
                {"kind": "part", "description": "Oil filter", "quantity": 2, "unit_price": 15},
            ],
        },
        headers=auth,
    )
    assert created.status_code == 201, created.text
    order = created.json()
    assert order["number"].startswith("SO-")
    assert len(order["items"]) == 2
    assert float(order["totals"]["total"]) == 90.0

    started = await client.post(
        f"/api/v1/service-orders/{order['id']}/status",
        json={"status": "in_progress"},
        headers=auth,
    )
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "in_progress"

    vehicle_row = await client.get(f"/api/v1/vehicles/{vehicle['id']}", headers=auth)
    assert vehicle_row.json()["status"] == "in_service"

    added = await client.post(
        f"/api/v1/service-orders/{order['id']}/items",
        json={"kind": "part", "description": "Bolt pack", "quantity": 1, "unit_price": 5},
        headers=auth,
    )
    assert added.status_code == 201
    assert len(added.json()["items"]) == 3

    completed = await client.post(
        f"/api/v1/service-orders/{order['id']}/status",
        json={"status": "completed"},
        headers=auth,
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"

    vehicle_row = await client.get(f"/api/v1/vehicles/{vehicle['id']}", headers=auth)
    assert vehicle_row.json()["status"] == "active"

    invoice_response = await client.post(
        "/api/v1/invoices/from-order",
        json={"order_id": order["id"], "due_days": 7},
        headers=auth,
    )
    assert invoice_response.status_code == 201, invoice_response.text
    invoice = invoice_response.json()
    assert invoice["number"].startswith("INV-")
    assert invoice["status"] == "draft"
    assert float(invoice["subtotal"]) == 95.0

    order_row = await client.get(f"/api/v1/service-orders/{order['id']}", headers=auth)
    assert order_row.json()["status"] == "invoiced"

    # Only completed orders can be invoiced — and only once.
    second = await client.post(
        "/api/v1/invoices/from-order",
        json={"order_id": order["id"], "due_days": 7},
        headers=auth,
    )
    assert second.status_code == 409

    sent = await client.post(
        f"/api/v1/invoices/{invoice['id']}/status",
        json={"status": "sent"},
        headers=auth,
    )
    assert sent.status_code == 200, sent.text

    paid = await client.post(
        f"/api/v1/invoices/{invoice['id']}/status",
        json={"status": "paid"},
        headers=auth,
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "paid"
    assert paid.json()["paid_at"] is not None

    stats = await client.get("/api/v1/dashboard/stats", headers=auth)
    assert stats.status_code == 200
    body = stats.json()
    assert body["customers_total"] == 1
    assert body["vehicles_total"] == 1
    assert float(body["revenue_30d"]) >= 95.0

    invoices = await client.get("/api/v1/invoices", headers=auth)
    assert invoices.status_code == 200
    assert invoices.json()["total"] == 1


async def test_free_plan_feature_gates(make_workspace):
    client, slug, _email, token = await make_workspace("gates")
    auth = _headers(slug, token)

    audited = await client.get("/api/v1/audit", headers=auth)
    assert audited.status_code == 402

    keys = await client.get("/api/v1/settings/api-keys", headers=auth)
    assert keys.status_code == 402

    domain = await client.post(
        "/api/v1/settings/domains", json={"domain": "service.example.com"}, headers=auth
    )
    assert domain.status_code == 402

    branding = await client.patch(
        "/api/v1/settings/branding",
        json={"primary_color": "#ff5500"},
        headers=auth,
    )
    assert branding.status_code == 402


async def test_role_enforcement_and_invites(make_workspace):
    client, slug, _email, token = await make_workspace("roles")
    auth = _headers(slug, token)

    staff = await client.post(
        "/api/v1/staff",
        json={
            "email": f"wrench@{slug}.example",
            "name": "Mike Torres",
            "password": "mechanic-pass-123",
            "role": "mechanic",
        },
        headers=auth,
    )
    assert staff.status_code == 201, staff.text

    from app.main import app

    mechanic_client = AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    )
    try:
        login = await mechanic_client.post(
            "/api/v1/auth/login",
            json={"email": f"wrench@{slug}.example", "password": "mechanic-pass-123"},
            headers={"X-Tenant-Slug": slug},
        )
        assert login.status_code == 200, login.text
        mechanic_auth = _headers(slug, login.json()["access_token"])

        customer = await _create_customer(client, slug, token, name="Delete Me")
        denied = await mechanic_client.delete(
            f"/api/v1/customers/{customer['id']}", headers=mechanic_auth
        )
        assert denied.status_code == 403

        # Mechanics can still create service orders (their daily job).
        vehicle = await _create_vehicle(client, slug, token, customer["id"])
        allowed = await mechanic_client.post(
            "/api/v1/service-orders",
            json={"vehicle_id": vehicle["id"], "description": "Brake inspection"},
            headers=mechanic_auth,
        )
        assert allowed.status_code == 201
    finally:
        await mechanic_client.aclose()


async def test_tenant_isolation_via_api(make_workspace):
    client_a, slug_a, _email_a, token_a = await make_workspace("iso-a")
    client_b, slug_b, _email_b, token_b = await make_workspace("iso-b")

    customer = await _create_customer(client_a, slug_a, token_a)
    vehicle = await _create_vehicle(client_a, slug_a, token_a, customer["id"])

    # B cannot read A's vehicle.
    denied = await client_b.get(
        f"/api/v1/vehicles/{vehicle['id']}", headers=_headers(slug_b, token_b)
    )
    assert denied.status_code == 404

    # B cannot create an order against A's vehicle. The reference fails
    # validation identically for "does not exist" and "belongs to another
    # tenant" — no existence oracle.
    cross = await client_b.post(
        "/api/v1/service-orders",
        json={"vehicle_id": vehicle["id"], "description": "Smuggled order"},
        headers=_headers(slug_b, token_b),
    )
    assert cross.status_code == 422, cross.text
    assert cross.json()["detail"] == "Vehicle not found"

    # B's lists are empty.
    listing = await client_b.get("/api/v1/vehicles", headers=_headers(slug_b, token_b))
    assert listing.status_code == 200
    assert listing.json()["total"] == 0

    stats = await client_b.get("/api/v1/dashboard/stats", headers=_headers(slug_b, token_b))
    assert stats.json()["vehicles_total"] == 0
    assert stats.json()["customers_total"] == 0

    # A still sees its data.
    own = await client_a.get("/api/v1/vehicles", headers=_headers(slug_a, token_a))
    assert own.json()["total"] == 1


async def test_unauthenticated_requests_rejected(make_workspace):
    client, slug, _email, _token = await make_workspace("noauth")

    for path in ("/api/v1/vehicles", "/api/v1/customers", "/api/v1/service-orders", "/api/v1/auth/me"):
        response = await client.get(path, headers={"X-Tenant-Slug": slug})
        assert response.status_code == 401, path

    garbage = await client.get(
        "/api/v1/vehicles",
        headers={"Authorization": "Bearer not.a.jwt", "X-Tenant-Slug": slug},
    )
    assert garbage.status_code == 401
