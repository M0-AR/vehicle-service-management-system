"""Tier C suppliers: connections, CSV catalogs, search and inventory import.

Both keyless providers (stub and csv) are exercised end to end through the
real ASGI stack, including RLS tenant isolation and plan gating.
"""

from __future__ import annotations

from test_api_flow import (  # fixtures/helpers reused across test modules
    _headers,
    make_workspace,  # noqa: F401  (pytest fixture)
)
from test_push import _create_mechanic, _login


async def _upgrade_to_pro(client, auth) -> None:
    response = await client.post(
        "/api/v1/settings/billing/checkout", json={"plan": "pro"}, headers=auth
    )
    assert response.status_code == 200, response.text


async def _create_supplier(
    client, auth, name: str = "Demo Distribution", **extra
) -> dict:
    response = await client.post(
        "/api/v1/suppliers",
        json={"name": name, "provider": "stub", **extra},
        headers=auth,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _csv_bytes(*rows: str) -> bytes:
    return ("\n".join(rows) + "\n").encode()


CATALOG_CSV = _csv_bytes(
    "sku,description,brand,cost,price,stock",
    "CSV-OIL-1,Oil filter premium,Mann,7.10,13.90,25",
    "CSV-BRK-9,Brake pad set front,Bosch,41.00,72.50,8",
    ",Broken row missing sku,,1,2,3",
    "CSV-BAD,Bad price row,,1,-2,3",
)


async def _upload(client, auth, connection_id: str, payload: bytes):
    return await client.post(
        f"/api/v1/suppliers/{connection_id}/catalog",
        files={"file": ("catalog.csv", payload, "text/csv")},
        headers=auth,
    )


async def test_suppliers_are_pro_gated(make_workspace):
    client, slug, _email, token = await make_workspace("supgate")
    auth = _headers(slug, token)

    response = await client.get("/api/v1/suppliers", headers=auth)
    assert response.status_code == 402, response.text
    response = await client.get(
        "/api/v1/suppliers/search", params={"q": "brake"}, headers=auth
    )
    assert response.status_code == 402, response.text


async def test_stub_search_import_and_delete(make_workspace):
    client, slug, _email, token = await make_workspace("suplife")
    auth = _headers(slug, token)
    await _upgrade_to_pro(client, auth)

    supplier = await _create_supplier(
        client, auth, portal_url="https://distributor.example/order"
    )
    assert supplier["provider"] == "stub"
    assert supplier["catalog_size"] == 0

    response = await client.get(
        "/api/v1/suppliers/search", params={"q": "brake"}, headers=auth
    )
    assert response.status_code == 200, response.text
    offers = response.json()
    assert offers, "stub catalog should match 'brake'"
    offer = next(row for row in offers if row["sku"] == "BP-3221")
    assert offer["supplier"] == "Demo Distribution"
    assert offer["portal_url"] == "https://distributor.example/order"

    response = await client.post(
        "/api/v1/suppliers/import",
        json={"connection_id": supplier["id"], "sku": "BP-3221"},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    imported = response.json()
    assert imported["created"] is True

    parts = await client.get(
        "/api/v1/inventory/parts", params={"q": "BP-3221"}, headers=auth
    )
    assert parts.status_code == 200, parts.text
    row = parts.json()["items"][0]
    assert row["supplier"] == "Demo Distribution"
    assert row["name"] == "Front brake pad set, ceramic"
    assert float(row["cost"]) == 38.40
    assert float(row["stock_qty"]) == 0
    assert row["id"] == imported["part_id"]

    response = await client.post(
        "/api/v1/suppliers/import",
        json={"connection_id": supplier["id"], "sku": "bp-3221"},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] is False
    assert response.json()["part_id"] == imported["part_id"]

    response = await client.get(
        "/api/v1/audit", params={"q": "supplier", "page_size": 20}, headers=auth
    )
    assert response.status_code == 200, response.text
    actions = {row["action"] for row in response.json()["items"]}
    assert {"supplier.created", "supplier.part_imported"} <= actions

    response = await client.delete(
        f"/api/v1/suppliers/{supplier['id']}", headers=auth
    )
    assert response.status_code == 200, response.text
    response = await client.get("/api/v1/suppliers", headers=auth)
    assert response.json() == []
    response = await client.get(
        "/api/v1/suppliers/search", params={"q": "brake"}, headers=auth
    )
    assert response.json() == []


async def test_csv_catalog_import_search_and_rules(make_workspace):
    client, slug, _email, token = await make_workspace("supcsv")
    auth = _headers(slug, token)
    await _upgrade_to_pro(client, auth)

    supplier = await _create_supplier(
        client, auth, name="Regional Parts Co", provider="csv"
    )

    response = await _upload(client, auth, supplier["id"], CATALOG_CSV)
    assert response.status_code == 200, response.text
    assert response.json() == {"imported": 2, "updated": 0, "skipped": 2}

    response = await client.get("/api/v1/suppliers", headers=auth)
    assert response.json()[0]["catalog_size"] == 2

    response = await client.get(
        "/api/v1/suppliers/search", params={"q": "oil"}, headers=auth
    )
    assert response.status_code == 200, response.text
    offers = response.json()
    assert [row["sku"] for row in offers] == ["CSV-OIL-1"]
    assert offers[0]["supplier"] == "Regional Parts Co"
    assert float(offers[0]["price"]) == 13.90

    response = await client.post(
        "/api/v1/suppliers/import",
        json={"connection_id": supplier["id"], "sku": "csv-oil-1"},
        headers=auth,
    )
    assert response.status_code == 200, response.text

    updated_csv = _csv_bytes(
        "sku,description,brand,cost,price,stock",
        "CSV-OIL-1,Oil filter premium,Mann,7.25,14.50,20",
        "CSV-BRK-9,Brake pad set front,Bosch,41.00,72.50,8",
    )
    response = await _upload(client, auth, supplier["id"], updated_csv)
    assert response.status_code == 200, response.text
    assert response.json() == {"imported": 0, "updated": 2, "skipped": 0}

    response = await client.get(
        "/api/v1/suppliers/search", params={"q": "CSV-OIL-1"}, headers=auth
    )
    assert float(response.json()[0]["price"]) == 14.50

    response = await client.post(
        "/api/v1/suppliers/import",
        json={"connection_id": supplier["id"], "sku": "CSV-OIL-1"},
        headers=auth,
    )
    assert response.json()["created"] is False
    parts = await client.get(
        "/api/v1/inventory/parts", params={"q": "CSV-OIL-1"}, headers=auth
    )
    assert float(parts.json()["items"][0]["price"]) == 14.50

    response = await _upload(
        client, auth, supplier["id"], _csv_bytes("name,qty", "x,1")
    )
    assert response.status_code == 400
    assert "missing required column" in response.json()["detail"]

    stub = await _create_supplier(client, auth, name="Stub Co")
    response = await _upload(client, auth, stub["id"], CATALOG_CSV)
    assert response.status_code == 400
    assert "CSV suppliers" in response.json()["detail"]

    response = await client.post(
        "/api/v1/suppliers/import",
        json={"connection_id": supplier["id"], "sku": "NOPE"},
        headers=auth,
    )
    assert response.status_code == 404

    await _create_mechanic(client, slug, token)
    mechanic = await _login(
        client, slug, f"wrench@{slug}.example", "mechanic-pass-123"
    )
    response = await _upload(client, mechanic, supplier["id"], CATALOG_CSV)
    assert response.status_code == 403, response.text
    response = await client.post(
        "/api/v1/suppliers",
        json={"name": "Mechanic Co", "provider": "stub"},
        headers=mechanic,
    )
    assert response.status_code == 403, response.text
    response = await client.get(
        "/api/v1/suppliers/search", params={"q": "oil"}, headers=mechanic
    )
    assert response.status_code == 200, response.text
    assert response.json()

    response = await client.get(
        "/api/v1/audit", params={"q": "supplier", "page_size": 20}, headers=auth
    )
    actions = {row["action"] for row in response.json()["items"]}
    assert {
        "supplier.catalog_imported",
        "supplier.part_imported",
    } <= actions


async def test_supplier_tenant_isolation(make_workspace):
    client_a, slug_a, _email_a, token_a = await make_workspace("supisoa")
    client_b, slug_b, _email_b, token_b = await make_workspace("supisob")
    auth_a = _headers(slug_a, token_a)
    auth_b = _headers(slug_b, token_b)
    await _upgrade_to_pro(client_a, auth_a)
    await _upgrade_to_pro(client_b, auth_b)

    supplier = await _create_supplier(
        client_a, auth_a, name="Shared Name", provider="csv"
    )
    response = await _upload(
        client_a,
        auth_a,
        supplier["id"],
        _csv_bytes("sku,description", "ISO-1,Isolated part"),
    )
    assert response.status_code == 200, response.text
    await _create_supplier(client_b, auth_b, name="Shared Name")

    response = await client_b.get("/api/v1/suppliers", headers=auth_b)
    assert len(response.json()) == 1
    assert response.json()[0]["id"] != supplier["id"]

    response = await client_b.delete(
        f"/api/v1/suppliers/{supplier['id']}", headers=auth_b
    )
    assert response.status_code == 404, response.text

    response = await client_a.get(
        "/api/v1/suppliers/search", params={"q": "ISO-1"}, headers=auth_a
    )
    assert [row["sku"] for row in response.json()] == ["ISO-1"]
    response = await client_b.get(
        "/api/v1/suppliers/search", params={"q": "ISO-1"}, headers=auth_b
    )
    assert response.json() == []
