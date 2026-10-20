"""Tier C accounting: entitlement, stub sync, idempotency, tenant isolation.

The provider is fixed by deployment; these tests run against the keyless stub
(the same code path the UI uses in local dev). QBO/Xero network calls share the
journal builder and are exercised by the payload-focused assertions below.
"""

from __future__ import annotations

from datetime import date

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


async def _paid_invoice(client, slug, token, auth, amount: float = 100.0) -> dict:
    customer = await _create_customer(client, slug, token)
    vehicle = await _create_vehicle(client, slug, token, customer["id"])
    order = await client.post(
        "/api/v1/service-orders",
        json={
            "vehicle_id": vehicle["id"],
            "description": "Accounting sync job",
            "items": [
                {
                    "kind": "labor",
                    "description": "Service labour",
                    "quantity": 1,
                    "unit_price": amount,
                }
            ],
        },
        headers=auth,
    )
    assert order.status_code == 201, order.text
    order_body = order.json()
    started = await client.post(
        f"/api/v1/service-orders/{order_body['id']}/status",
        json={"status": "in_progress"},
        headers=auth,
    )
    assert started.status_code == 200, started.text
    completed = await client.post(
        f"/api/v1/service-orders/{order_body['id']}/status",
        json={"status": "completed"},
        headers=auth,
    )
    assert completed.status_code == 200, completed.text
    invoice = await client.post(
        "/api/v1/invoices/from-order",
        json={"order_id": order_body["id"], "due_days": 7},
        headers=auth,
    )
    assert invoice.status_code == 201, invoice.text
    invoice_body = invoice.json()
    paid = await client.post(
        f"/api/v1/invoices/{invoice_body['id']}/status",
        json={"status": "paid"},
        headers=auth,
    )
    assert paid.status_code == 200, paid.text
    return paid.json()


async def test_accounting_is_pro_gated(make_workspace):
    client, slug, _email, token = await make_workspace("gateacct")
    auth = _headers(slug, token)

    blocked = await client.get("/api/v1/accounting", headers=auth)
    assert blocked.status_code == 402, blocked.text

    await _upgrade_to_pro(client, auth)
    allowed = await client.get("/api/v1/accounting", headers=auth)
    assert allowed.status_code == 200, allowed.text
    body = allowed.json()
    assert body["provider"] == "stub"
    assert body["configured"] is True
    assert body["connection"] is None

    runs = await client.get("/api/v1/accounting/runs", headers=auth)
    assert runs.status_code == 200, runs.text
    assert runs.json()["total"] == 0


async def test_stub_connect_sync_is_idempotent_and_exports(make_workspace):
    client, slug, _email, token = await make_workspace("acctsync")
    auth = _headers(slug, token)
    await _upgrade_to_pro(client, auth)

    invoice = await _paid_invoice(client, slug, token, auth, amount=100)
    today = date.today().isoformat()

    before = await client.get("/api/v1/accounting", headers=auth)
    assert before.json()["pending_invoices"] == 1

    connected = await client.post("/api/v1/accounting/connect", headers=auth)
    assert connected.status_code == 200, connected.text
    assert connected.json()["connected"] is True

    mapping = await client.patch(
        "/api/v1/accounting/connection",
        json={"payment": "1010", "income": "4010", "tax": "2210"},
        headers=auth,
    )
    assert mapping.status_code == 200, mapping.text
    assert mapping.json()["connection"]["accounts"] == {
        "payment": "1010",
        "income": "4010",
        "tax": "2210",
    }

    synced = await client.post(
        "/api/v1/accounting/sync",
        json={"period_start": today, "period_end": today},
        headers=auth,
    )
    assert synced.status_code == 201, synced.text
    run = synced.json()
    assert run["status"] == "succeeded"
    assert run["invoices_count"] == 1
    assert float(run["total_amount"]) == 100.0

    after = await client.get("/api/v1/accounting", headers=auth)
    assert after.json()["pending_invoices"] == 0
    assert after.json()["connection"]["last_synced_at"] is not None

    exported = await client.get(
        f"/api/v1/accounting/export?period_start={today}&period_end={today}",
        headers=auth,
    )
    assert exported.status_code == 200, exported.text
    assert "text/csv" in exported.headers["content-type"]
    csv_body = exported.text
    assert invoice["number"] in csv_body
    assert "1010" in csv_body
    assert "4010" in csv_body
    assert ",100.00,0.00," in csv_body

    again = await client.post(
        "/api/v1/accounting/sync",
        json={"period_start": today, "period_end": today},
        headers=auth,
    )
    assert again.status_code == 201, again.text
    assert again.json()["invoices_count"] == 0

    runs = await client.get("/api/v1/accounting/runs", headers=auth)
    assert runs.json()["total"] == 2

    removed = await client.delete("/api/v1/accounting/connection", headers=auth)
    assert removed.status_code == 204, removed.text
    assert (await client.get("/api/v1/accounting", headers=auth)).json()[
        "connection"
    ] is None


async def test_accounting_is_tenant_isolated(make_workspace):
    client_a, slug_a, _email_a, token_a = await make_workspace("accta")
    client_b, slug_b, _email_b, token_b = await make_workspace("acctb")
    auth_a = _headers(slug_a, token_a)
    auth_b = _headers(slug_b, token_b)
    await _upgrade_to_pro(client_a, auth_a)
    await _upgrade_to_pro(client_b, auth_b)

    assert (
        await client_a.post("/api/v1/accounting/connect", headers=auth_a)
    ).status_code == 200
    status_b = await client_b.get("/api/v1/accounting", headers=auth_b)
    assert status_b.json()["connection"] is None
    runs_b = await client_b.get("/api/v1/accounting/runs", headers=auth_b)
    assert runs_b.json()["total"] == 0


async def test_unconfigured_provider_returns_guidance(make_workspace, monkeypatch):
    from app.services import accounting

    client, slug, _email, token = await make_workspace("acctcfg")
    auth = _headers(slug, token)
    await _upgrade_to_pro(client, auth)

    monkeypatch.setattr(accounting.settings, "accounting_provider", "quickbooks")
    monkeypatch.setattr(accounting.settings, "quickbooks_client_id", "")
    monkeypatch.setattr(accounting.settings, "quickbooks_client_secret", "")

    status = await client.get("/api/v1/accounting", headers=auth)
    assert status.status_code == 200, status.text
    assert status.json()["configured"] is False

    blocked = await client.post("/api/v1/accounting/connect", headers=auth)
    assert blocked.status_code == 409, blocked.text
    assert "not configured" in blocked.json()["detail"].lower()
