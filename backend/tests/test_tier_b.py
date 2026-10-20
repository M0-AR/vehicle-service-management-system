"""Tier B flows: online payments, SMS outbox, DVI, booking, reviews.

All through the real ASGI stack (auth -> RLS -> Postgres), with provider calls
either config-gated or monkeypatched — no network access in tests.
"""

from __future__ import annotations

import secrets

from test_api_flow import (  # fixtures/helpers reused across test modules
    _create_customer,
    _create_vehicle,
    _headers,
    make_workspace,  # noqa: F401  (pytest fixture)
)

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _upgrade_to_pro(client, auth) -> None:
    response = await client.post(
        "/api/v1/settings/billing/checkout", json={"plan": "pro"}, headers=auth
    )
    assert response.status_code == 200, response.text


async def _completed_order(client, slug, token, auth) -> dict:
    customer = await _create_customer(client, slug, token)
    vehicle = await _create_vehicle(client, slug, token, customer["id"])
    created = await client.post(
        "/api/v1/service-orders",
        json={
            "vehicle_id": vehicle["id"],
            "description": "Brake service",
            "items": [
                {
                    "kind": "labor",
                    "description": "Replace front pads",
                    "quantity": 1,
                    "unit_price": 120,
                }
            ],
        },
        headers=auth,
    )
    assert created.status_code == 201, created.text
    order = created.json()
    started = await client.post(
        f"/api/v1/service-orders/{order['id']}/status",
        json={"status": "in_progress"},
        headers=auth,
    )
    assert started.status_code == 200, started.text
    completed = await client.post(
        f"/api/v1/service-orders/{order['id']}/status",
        json={"status": "completed"},
        headers=auth,
    )
    assert completed.status_code == 200, completed.text
    return completed.json()


async def test_tier_b_features_are_pro_gated(make_workspace):
    client, slug, _email, token = await make_workspace("gatesb")
    auth = _headers(slug, token)

    customer = await _create_customer(client, slug, token)
    vehicle = await _create_vehicle(client, slug, token, customer["id"])
    order = await client.post(
        "/api/v1/service-orders",
        json={"vehicle_id": vehicle["id"], "description": "Check brakes"},
        headers=auth,
    )
    order_id = order.json()["id"]

    dvi = await client.get(f"/api/v1/inspections/by-order/{order_id}", headers=auth)
    assert dvi.status_code == 402
    assert "upgrade" in dvi.json()["detail"].lower()

    sms = await client.post(
        "/api/v1/notifications/test",
        json={"to": "+15550001111"},
        headers=auth,
    )
    assert sms.status_code == 402

    await _upgrade_to_pro(client, auth)
    dvi = await client.get(f"/api/v1/inspections/by-order/{order_id}", headers=auth)
    assert dvi.status_code == 200


async def test_dvi_with_photo_and_public_status(make_workspace):
    client, slug, _email, token = await make_workspace("dvi")
    auth = _headers(slug, token)
    await _upgrade_to_pro(client, auth)
    order = await _completed_order(client, slug, token, auth)

    created = await client.post(
        f"/api/v1/inspections/by-order/{order['id']}",
        json={"notes": "Lift inspection"},
        headers=auth,
    )
    assert created.status_code == 201, created.text
    inspection = created.json()

    item = await client.post(
        f"/api/v1/inspections/{inspection['id']}/items",
        json={"label": "Front brake pads", "status": "attention", "note": "6mm left"},
        headers=auth,
    )
    assert item.status_code == 201, item.text
    item_id = item.json()["items"][0]["id"]

    upload = await client.post(
        f"/api/v1/inspections/{inspection['id']}/items/{item_id}/photos",
        files={"file": ("brake.png", PNG_BYTES, "image/png")},
        headers=auth,
    )
    assert upload.status_code == 200, upload.text
    photo = upload.json()["items"][0]["photos"][0]
    assert photo["mime"] == "image/png"

    bad = await client.post(
        f"/api/v1/inspections/{inspection['id']}/items/{item_id}/photos",
        files={"file": ("evil.png", b"<svg onload=alert(1)>", "image/png")},
        headers=auth,
    )
    assert bad.status_code == 422

    done = await client.patch(
        f"/api/v1/inspections/{inspection['id']}",
        json={"status": "completed"},
        headers=auth,
    )
    assert done.status_code == 200

    share = await client.post(
        f"/api/v1/service-orders/{order['id']}/share", headers=auth
    )
    share_token = share.json()["token"]
    public = await client.get(f"/api/v1/public/orders/{share_token}")
    assert public.status_code == 200, public.text
    body = public.json()
    assert body["inspection_completed"] is True
    assert body["inspection"][0]["label"] == "Front brake pads"
    assert body["inspection"][0]["photos"][0].startswith("/api/v1/public/orders/")

    photo_url = body["inspection"][0]["photos"][0]
    served = await client.get(photo_url)
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"


async def test_order_completion_queues_sms_outbox(make_workspace):
    client, slug, _email, token = await make_workspace("sms")
    auth = _headers(slug, token)
    await _upgrade_to_pro(client, auth)
    order = await _completed_order(client, slug, token, auth)

    log = await client.get("/api/v1/notifications", headers=auth)
    assert log.status_code == 200, log.text
    rows = log.json()["items"]
    ready = [r for r in rows if r["template"] == "order_ready"]
    assert len(ready) == 1
    assert ready[0]["entity_id"] == order["id"]
    # No provider configured in tests: recorded, not sent.
    assert ready[0]["status"] == "skipped"
    assert "ready for pickup" in ready[0]["body"]


async def test_public_booking_creates_scheduled_order(make_workspace):
    client, slug, _email, token = await make_workspace("book")
    auth = _headers(slug, token)
    await _upgrade_to_pro(client, auth)

    enabled = await client.patch(
        "/api/v1/settings/profile",
        json={"booking_enabled": True, "business_hours": {"mon": [["09:00", "17:00"]]}},
        headers=auth,
    )
    assert enabled.status_code == 200, enabled.text

    page = await client.get(f"/api/v1/public/booking/{slug}")
    assert page.status_code == 200, page.text
    slots = [s for s in page.json()["slots"] if s["available"]]
    assert slots, "expected at least one available slot"
    slot = slots[0]["start"]

    submitted = await client.post(
        f"/api/v1/public/booking/{slug}",
        json={
            "name": "Nadia Karam",
            "phone": "+15550199",
            "email": "nadia@example.com",
            "plate_number": "bkg123",
            "make": "Kia",
            "model": "Sportage",
            "year": 2021,
            "service_description": "AC not cooling",
            "preferred_at": slot,
        },
    )
    assert submitted.status_code == 201, submitted.text
    result = submitted.json()
    assert result["number"].startswith("SO-")

    orders = await client.get("/api/v1/service-orders", headers=auth)
    assert orders.status_code == 200
    created = [
        o for o in orders.json()["items"] if o["number"] == result["number"]
    ]
    assert created and created[0]["status"] == "scheduled"

    duplicate = await client.post(
        f"/api/v1/public/booking/{slug}",
        json={
            "name": "Nadia Karam",
            "phone": "+15550199",
            "plate_number": "BKG123",
            "service_description": "AC not cooling",
            "preferred_at": slot,
        },
    )
    assert duplicate.status_code == 201

    # Honeypot submissions create nothing but look successful to bots.
    honeypot = await client.post(
        f"/api/v1/public/booking/{slug}",
        json={
            "name": "Bot",
            "phone": "+15550000",
            "plate_number": "BOT1",
            "service_description": "spam",
            "preferred_at": slot,
            "company": "SpamCo",
        },
    )
    assert honeypot.status_code == 201


async def test_review_request_and_public_submission(make_workspace):
    client, slug, _email, token = await make_workspace("review")
    auth = _headers(slug, token)
    await _upgrade_to_pro(client, auth)
    order = await _completed_order(client, slug, token, auth)

    created = await client.post(
        f"/api/v1/service-orders/{order['id']}/review-request", headers=auth
    )
    assert created.status_code == 201, created.text
    review = created.json()
    assert review["url_path"].startswith("/review/")
    token_part = review["url_path"].rsplit("/", 1)[1]

    page = await client.get(f"/api/v1/public/reviews/{token_part}")
    assert page.status_code == 200, page.text
    assert page.json()["status"] == "pending"

    submitted = await client.post(
        f"/api/v1/public/reviews/{token_part}",
        json={"rating": 5, "comment": "Fast and friendly"},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"
    assert submitted.json()["rating"] == 5

    again = await client.post(
        f"/api/v1/public/reviews/{token_part}",
        json={"rating": 1},
    )
    assert again.status_code == 409

    rerun = await client.post(
        f"/api/v1/service-orders/{order['id']}/review-request", headers=auth
    )
    assert rerun.status_code == 201, rerun.text
    assert rerun.json()["url_path"] != review["url_path"]
    outbox = await client.get("/api/v1/notifications", headers=auth)
    assert outbox.status_code == 200, outbox.text
    rows = outbox.json()["items"]
    assert len(rows) == 3, rows  # order_ready + original + rerun
    reviews = [r for r in rows if r["template"] == "review_request"]
    assert len(reviews) == 2, reviews
    assert rerun.json()["url_path"] in rows[0]["body"]


async def test_invoice_payment_link_requires_stripe_config(make_workspace, monkeypatch):
    client, slug, _email, token = await make_workspace("pay")
    auth = _headers(slug, token)
    await _upgrade_to_pro(client, auth)
    order = await _completed_order(client, slug, token, auth)

    invoice = await client.post(
        "/api/v1/invoices/from-order", json={"order_id": order["id"]}, headers=auth
    )
    assert invoice.status_code == 201, invoice.text
    invoice_id = invoice.json()["id"]

    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "billing_provider", "stripe")
    monkeypatch.setattr(get_settings(), "stripe_secret_key", "")
    unconfigured = await client.post(
        f"/api/v1/invoices/{invoice_id}/payment-link", headers=auth
    )
    assert unconfigured.status_code == 409
    assert "stripe" in unconfigured.json()["detail"].lower()

    async def fake_checkout(self, **kwargs):
        return "https://checkout.stripe.test/session", "Redirecting to secure payment."

    from app.services.billing.stripe import StripeProvider

    monkeypatch.setattr(StripeProvider, "create_payment_checkout", fake_checkout)
    linked = await client.post(
        f"/api/v1/invoices/{invoice_id}/payment-link", headers=auth
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["url"].startswith("https://checkout.stripe.test/")

    refreshed = await client.get(f"/api/v1/invoices/{invoice_id}", headers=auth)
    assert refreshed.json()["payment_url"] == linked.json()["url"]
    assert refreshed.json()["payment_provider"] == "stripe"
    assert refreshed.json()["status"] == "sent"


async def test_stripe_invoice_webhook_marks_paid(make_workspace, monkeypatch):
    import hashlib
    import hmac
    import json
    import time

    from app.core.config import get_settings

    client, slug, _email, token = await make_workspace("payhook")
    auth = _headers(slug, token)
    await _upgrade_to_pro(client, auth)
    order = await _completed_order(client, slug, token, auth)
    invoice = await client.post(
        "/api/v1/invoices/from-order", json={"order_id": order["id"]}, headers=auth
    )
    invoice_body = invoice.json()

    secret = "whsec_test_secret"
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", secret)
    payload = {
        "id": f"evt_{secrets.token_hex(6)}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "payment_status": "paid",
                "metadata": {
                    "tenant_id": invoice_body["meta"].get("tenant_id")
                    or str(order["vehicle_id"]),
                    "invoice_id": invoice_body["id"],
                },
            }
        },
    }
    # Resolve the real tenant id through the auth context's tenant.
    from sqlalchemy import text

    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        tenant_id = (
            await session.execute(
                text("SELECT id FROM tenants WHERE slug = :s"), {"s": slug}
            )
        ).scalar_one()
    payload["data"]["object"]["metadata"]["tenant_id"] = str(tenant_id)

    raw = json.dumps(payload).encode()
    ts = str(int(time.time()))
    signature = hmac.new(
        secret.encode(), f"{ts}.{raw.decode()}".encode(), hashlib.sha256
    ).hexdigest()
    response = await client.post(
        "/api/v1/webhooks/billing/stripe",
        content=raw,
        headers={
            "Stripe-Signature": f"t={ts},v1={signature}",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["applied"] is True

    refreshed = await client.get(f"/api/v1/invoices/{invoice_body['id']}", headers=auth)
    assert refreshed.json()["status"] == "paid"
    assert refreshed.json()["paid_at"] is not None
