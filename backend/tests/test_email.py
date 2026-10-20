"""Email channel: SMTP config gate, send path, campaign integration.

The transport (`_smtp_send`) is monkeypatched so the suite stays offline; the
outbox, entitlement and status plumbing runs against real Postgres.
"""

from __future__ import annotations

import smtplib

from test_api_flow import _headers, make_workspace  # noqa: F401


def _smtp_settings(monkeypatch, **overrides):
    from app.services import notifications

    values = {
        "smtp_host": "smtp.example.com",
        "smtp_port": 2525,
        "smtp_username": "",
        "smtp_password": "",
        "smtp_from": "Downtown Auto Care <no-reply@shop.example>",
        "smtp_security": "starttls",
        "smtp_timeout": 5.0,
        **overrides,
    }
    for key, value in values.items():
        monkeypatch.setattr(notifications.settings, key, value, raising=False)
    return notifications


async def test_email_unconfigured_is_skipped_with_guidance(make_workspace):
    client, slug, _email, token = await make_workspace("mailoff")
    auth = _headers(slug, token)

    response = await client.post(
        "/api/v1/notifications/test",
        json={"channel": "email", "to": "owner@example.com"},
        headers=auth,
    )
    assert response.status_code == 409, response.text
    assert "SMTP_HOST" in response.json()["detail"]

    from app.services import notifications

    assert notifications.email_configured() is False
    status, error = await notifications.send_email("a@example.com", "Subject", "Body")
    assert status == "skipped"
    assert error == "Email provider is not configured"

    outbox = await client.get(
        "/api/v1/notifications", params={"channel": "email"}, headers=auth
    )
    assert outbox.status_code == 200, outbox.text
    assert outbox.json()["total"] == 0


async def test_email_test_send_marks_sent_and_sets_provider(
    make_workspace, monkeypatch
):
    notifications = _smtp_settings(monkeypatch)
    captured: list = []
    monkeypatch.setattr(notifications, "_smtp_send", captured.append)

    client, slug, _email, token = await make_workspace("mailon")
    auth = _headers(slug, token)

    response = await client.post(
        "/api/v1/notifications/test",
        json={
            "channel": "email",
            "to": "customer@example.com",
            "message": "Hello there",
        },
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "sent"
    assert body["provider"] == "smtp"
    assert body["sent_at"] is not None

    assert len(captured) == 1
    message = captured[0]
    assert message["To"] == "customer@example.com"
    assert message["From"] == "Downtown Auto Care <no-reply@shop.example>"
    assert message["Subject"] == "Test message"
    assert "Hello there" in message.get_content()


async def test_email_failure_records_error(make_workspace, monkeypatch):
    notifications = _smtp_settings(monkeypatch)

    def boom(message):
        raise smtplib.SMTPServerDisconnected("connection lost")

    monkeypatch.setattr(notifications, "_smtp_send", boom)

    client, slug, _email, token = await make_workspace("mailfail")
    auth = _headers(slug, token)
    response = await client.post(
        "/api/v1/notifications/test",
        json={"channel": "email", "to": "customer@example.com"},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["provider"] == "smtp"
    assert "connection lost" in (body["error"] or "")


async def test_unknown_smtp_security_fails_cleanly(make_workspace, monkeypatch):
    _smtp_settings(monkeypatch, smtp_security="pigeon")

    client, slug, _email, token = await make_workspace("mailsec")
    auth = _headers(slug, token)
    response = await client.post(
        "/api/v1/notifications/test",
        json={"channel": "email", "to": "customer@example.com"},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert "SMTP_SECURITY" in (body["error"] or "")


async def test_campaign_email_send_is_delivered_when_configured(
    make_workspace, monkeypatch
):
    notifications = _smtp_settings(monkeypatch)
    sent_messages: list = []
    monkeypatch.setattr(notifications, "_smtp_send", sent_messages.append)

    client, slug, _email, token = await make_workspace("mailcamp")
    auth = _headers(slug, token)

    checkout = await client.post(
        "/api/v1/settings/billing/checkout", json={"plan": "pro"}, headers=auth
    )
    assert checkout.status_code == 200, checkout.text

    created = await client.post(
        "/api/v1/customers",
        json={"name": "Email Client", "email": "client@example.com"},
        headers=auth,
    )
    assert created.status_code == 201, created.text

    campaign = await client.post(
        "/api/v1/campaigns",
        json={
            "name": "Email blast",
            "channel": "email",
            "segment": "all",
            "lookback_days": 90,
            "body": "Hi {name}, news from {shop}.",
        },
        headers=auth,
    )
    assert campaign.status_code == 201, campaign.text

    sent = await client.post(
        f"/api/v1/campaigns/{campaign.json()['id']}/send", headers=auth
    )
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert body["sent_count"] == 1
    assert body["skipped_count"] == 0

    assert len(sent_messages) == 1
    assert sent_messages[0]["To"] == "client@example.com"
    assert "Email Client" in sent_messages[0].get_content()

    detail = await client.get(
        f"/api/v1/campaigns/{campaign.json()['id']}", headers=auth
    )
    assert detail.json()["recipients"][0]["status"] == "sent"
