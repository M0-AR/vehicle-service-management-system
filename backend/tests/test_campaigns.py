"""Tier C marketing: entitlement, segment math, outbox send, tenant isolation.

Segments are date-windowed, so one order is backdated with a direct admin
connection (the API only stamps `completed_at = now()`); delivery runs through
the real notification outbox, which records `skipped` rows when no SMS/email
provider is configured — the honest behaviour a keyless deployment gets.
"""

from __future__ import annotations

import os

import asyncpg

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


async def _admin_execute(query: str, *args) -> None:
    dsn = os.environ["MIGRATION_DATABASE_URL"].replace("+asyncpg", "")
    conn = await asyncpg.connect(dsn=dsn)
    try:
        await conn.execute(query, *args)
    finally:
        await conn.close()


async def _customer(client, slug, token, name: str, phone=None, email=None) -> dict:
    payload: dict = {"name": name}
    if phone is not None:
        payload["phone"] = phone
    if email is not None:
        payload["email"] = email
    response = await client.post(
        "/api/v1/customers", json=payload, headers=_headers(slug, token)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _completed_order(client, slug, token, auth, customer_id: str) -> dict:
    vehicle = await _create_vehicle(client, slug, token, customer_id)
    created = await client.post(
        "/api/v1/service-orders",
        json={
            "vehicle_id": vehicle["id"],
            "description": "Campaign segment fixture",
            "items": [
                {"kind": "labor", "description": "Service", "quantity": 1, "unit_price": 50}
            ],
        },
        headers=auth,
    )
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    for status in ("in_progress", "completed"):
        moved = await client.post(
            f"/api/v1/service-orders/{order_id}/status",
            json={"status": status},
            headers=auth,
        )
        assert moved.status_code == 200, moved.text
    return created.json()


async def _preview(client, auth, *, channel="sms", segment="all", lookback=90) -> dict:
    response = await client.post(
        "/api/v1/campaigns/preview",
        json={"channel": channel, "segment": segment, "lookback_days": lookback},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_campaigns_are_pro_gated(make_workspace):
    client, slug, _email, token = await make_workspace("gatecamp")
    auth = _headers(slug, token)

    blocked = await client.get("/api/v1/campaigns", headers=auth)
    assert blocked.status_code == 402, blocked.text
    assert "marketing" in blocked.json()["detail"].lower()

    await _upgrade_to_pro(client, auth)
    allowed = await client.get("/api/v1/campaigns", headers=auth)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["total"] == 0

    empty = await _preview(client, auth)
    assert empty == {"customers_count": 0, "recipients_count": 0}


async def test_segments_preview_and_send_records_skipped(make_workspace):
    client, slug, _email, token = await make_workspace("campsend")
    auth = _headers(slug, token)
    await _upgrade_to_pro(client, auth)

    never = await _customer(client, slug, token, "Never Serviced", phone="+1-555-0201")
    recent = await _customer(client, slug, token, "Recent Client", phone="+1-555-0202")
    overdue = await _customer(client, slug, token, "Overdue Client", phone="+1-555-0203")
    emailless = await _customer(
        client, slug, token, "Email Only Client", email="only@example.com"
    )
    assert all((never, recent, overdue, emailless))

    recent_order = await _completed_order(client, slug, token, auth, recent["id"])
    overdue_order = await _completed_order(client, slug, token, auth, overdue["id"])
    assert recent_order and overdue_order
    await _admin_execute(
        "UPDATE service_orders SET completed_at = now() - interval '200 days'"
        " WHERE id = $1",
        overdue_order["id"],
    )

    all_sms = await _preview(client, auth, segment="all", channel="sms")
    assert all_sms == {"customers_count": 4, "recipients_count": 3}

    all_email = await _preview(client, auth, segment="all", channel="email")
    assert all_email == {"customers_count": 4, "recipients_count": 1}

    inactive = await _preview(client, auth, segment="inactive", channel="sms", lookback=90)
    assert inactive == {"customers_count": 2, "recipients_count": 1}

    due = await _preview(client, auth, segment="due_service", channel="sms", lookback=180)
    assert due == {"customers_count": 1, "recipients_count": 1}

    created = await client.post(
        "/api/v1/campaigns",
        json={
            "name": "Overdue reminder",
            "channel": "sms",
            "segment": "due_service",
            "lookback_days": 180,
            "body": "Hi {name}, your service at {shop} is due.",
        },
        headers=auth,
    )
    assert created.status_code == 201, created.text
    campaign = created.json()
    assert campaign["status"] == "draft"
    assert campaign["recipients_count"] == 0

    sent = await client.post(
        f"/api/v1/campaigns/{campaign['id']}/send", headers=auth
    )
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert body["status"] == "sent"
    assert body["recipients_count"] == 1
    assert body["sent_count"] == 0
    assert body["skipped_count"] == 1
    assert body["failed_count"] == 0
    assert body["sent_at"] is not None

    detail = await client.get(f"/api/v1/campaigns/{campaign['id']}", headers=auth)
    assert detail.status_code == 200, detail.text
    recipients = detail.json()["recipients"]
    assert len(recipients) == 1
    assert recipients[0]["recipient"] == "+1-555-0203"
    assert recipients[0]["status"] == "skipped"
    assert recipients[0]["error"]

    resend = await client.post(
        f"/api/v1/campaigns/{campaign['id']}/send", headers=auth
    )
    assert resend.status_code == 409, resend.text

    undeletable = await client.delete(
        f"/api/v1/campaigns/{campaign['id']}", headers=auth
    )
    assert undeletable.status_code == 409, undeletable.text

    draft = await client.post(
        "/api/v1/campaigns",
        json={
            "name": "Scratch",
            "channel": "email",
            "segment": "all",
            "body": "Hello {name}",
        },
        headers=auth,
    )
    assert draft.status_code == 201, draft.text
    removed = await client.delete(
        f"/api/v1/campaigns/{draft.json()['id']}", headers=auth
    )
    assert removed.status_code == 204, removed.text

    listing = await client.get("/api/v1/campaigns", headers=auth)
    assert listing.json()["total"] == 1


async def test_campaign_send_rejects_empty_audience(make_workspace):
    client, slug, _email, token = await make_workspace("campempty")
    auth = _headers(slug, token)
    await _upgrade_to_pro(client, auth)

    await _customer(client, slug, token, "No Contact", phone=None, email=None)

    created = await client.post(
        "/api/v1/campaigns",
        json={
            "name": "Nobody",
            "channel": "sms",
            "segment": "all",
            "body": "Hello {name}",
        },
        headers=auth,
    )
    assert created.status_code == 201, created.text
    blocked = await client.post(
        f"/api/v1/campaigns/{created.json()['id']}/send", headers=auth
    )
    assert blocked.status_code == 422, blocked.text
    assert "no reachable customers" in blocked.json()["detail"].lower()


async def test_campaigns_are_tenant_isolated(make_workspace):
    client_a, slug_a, _email_a, token_a = await make_workspace("campa")
    client_b, slug_b, _email_b, token_b = await make_workspace("campb")
    auth_a = _headers(slug_a, token_a)
    auth_b = _headers(slug_b, token_b)
    await _upgrade_to_pro(client_a, auth_a)
    await _upgrade_to_pro(client_b, auth_b)

    created = await client_a.post(
        "/api/v1/campaigns",
        json={
            "name": "Private",
            "channel": "sms",
            "segment": "all",
            "body": "Hi {name}",
        },
        headers=auth_a,
    )
    assert created.status_code == 201, created.text

    listing_b = await client_b.get("/api/v1/campaigns", headers=auth_b)
    assert listing_b.json()["total"] == 0
    peek = await client_b.get(
        f"/api/v1/campaigns/{created.json()['id']}", headers=auth_b
    )
    assert peek.status_code == 404, peek.text


async def test_campaign_lookback_window(make_workspace):
    client, slug, _email, token = await make_workspace("campwin")
    auth = _headers(slug, token)
    await _upgrade_to_pro(client, auth)

    overdue = await _customer(client, slug, token, "Windowed", phone="+1-555-0301")
    order = await _completed_order(client, slug, token, auth, overdue["id"])
    await _admin_execute(
        "UPDATE service_orders SET completed_at = now() - interval '200 days'"
        " WHERE id = $1",
        order["id"],
    )

    wide = await _preview(client, auth, segment="due_service", lookback=365)
    assert wide["recipients_count"] == 0
    narrow = await _preview(client, auth, segment="due_service", lookback=90)
    assert narrow["recipients_count"] == 1