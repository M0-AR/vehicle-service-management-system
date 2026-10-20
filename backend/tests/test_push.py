"""Tier C: staff Web Push — config, subscriptions, delivery, triggers.

The VAPID keypair is deployment-wide: generated once into `push_config` when
envs are empty, and identical for every tenant. Subscriptions are per-device
and tenant-scoped (RLS); delivery is best-effort and prunes dead endpoints.
`pywebpush.webpush` is monkeypatched — no test ever talks to a push service.
"""

from __future__ import annotations

from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient

from test_api_flow import _headers, make_workspace  # noqa: F401  (fixture)

P256DH = "BNcR1Jv0VYyexamplekeymaterial000000000000000000000000000000000000000"
AUTH = "k9Xf2example-auth-secret"


async def _upgrade_to_pro(client, auth) -> None:
    response = await client.post(
        "/api/v1/settings/billing/checkout", json={"plan": "pro"}, headers=auth
    )
    assert response.status_code == 200, response.text


def _subscription(endpoint: str, **extra) -> dict:
    return {
        "endpoint": endpoint,
        "keys": {"p256dh": P256DH, "auth": AUTH},
        **extra,
    }


class _FakeWebPushError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"push failed with {status_code}")
        self.response = SimpleNamespace(status_code=status_code)


class _FakeWebPush:
    """Records every delivery attempt; endpoints containing 'gone' expire."""

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, *, subscription_info, data, vapid_private_key, vapid_claims, timeout=None):
        endpoint = subscription_info["endpoint"]
        self.calls.append(endpoint)
        if "gone" in endpoint:
            raise _FakeWebPushError(410)
        return SimpleNamespace(status_code=201)


async def _create_mechanic(client, slug: str, token: str) -> dict:
    response = await client.post(
        "/api/v1/staff",
        json={
            "email": f"wrench@{slug}.example",
            "name": "Mike Torres",
            "password": "mechanic-pass-123",
            "role": "mechanic",
        },
        headers=_headers(slug, token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _login(client, slug: str, email: str, password: str) -> dict:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"X-Tenant-Slug": slug},
    )
    assert response.status_code == 200, response.text
    return _headers(slug, response.json()["access_token"])


async def test_push_config_is_stable_and_subscriptions_upsert(make_workspace):
    client, slug, _email, token = await make_workspace("pushcfg")
    auth = _headers(slug, token)

    config = await client.get("/api/v1/push/config", headers=auth)
    assert config.status_code == 200, config.text
    body = config.json()
    assert body["enabled"] is True
    assert body["public_key"]

    again = await client.get("/api/v1/push/config", headers=auth)
    assert again.json()["public_key"] == body["public_key"]

    endpoint = f"https://push.example.com/ep-{slug}-one"
    created = await client.post(
        "/api/v1/push/subscriptions",
        json=_subscription(endpoint, user_agent="Test Browser"),
        headers=auth,
    )
    assert created.status_code == 201, created.text
    first = created.json()

    resubscribed = await client.post(
        "/api/v1/push/subscriptions",
        json=_subscription(endpoint, user_agent="Test Browser v2"),
        headers=auth,
    )
    assert resubscribed.status_code == 201, resubscribed.text
    assert resubscribed.json()["id"] == first["id"]

    listed = await client.get("/api/v1/push/subscriptions", headers=auth)
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["user_agent"] == "Test Browser v2"

    # The keypair is deployment-wide: another tenant sees the same public key.
    client_b, slug_b, _email_b, token_b = await make_workspace("pushcfg-b")
    config_b = await client_b.get("/api/v1/push/config", headers=_headers(slug_b, token_b))
    assert config_b.json()["public_key"] == body["public_key"]

    # …but the subscription list is tenant-scoped.
    listed_b = await client_b.get(
        "/api/v1/push/subscriptions", headers=_headers(slug_b, token_b)
    )
    assert listed_b.status_code == 200
    assert listed_b.json() == []


async def test_subscription_delete_is_own_device_or_admin(make_workspace):
    client, slug, _email, token = await make_workspace("pushdel")
    auth = _headers(slug, token)
    await _create_mechanic(client, slug, token)
    mechanic_auth = await _login(client, slug, f"wrench@{slug}.example", "mechanic-pass-123")

    owner_row = (
        await client.post(
            "/api/v1/push/subscriptions",
            json=_subscription(f"https://push.example.com/ep-{slug}-owner"),
            headers=auth,
        )
    ).json()
    mechanic_row = (
        await client.post(
            "/api/v1/push/subscriptions",
            json=_subscription(f"https://push.example.com/ep-{slug}-mech"),
            headers=mechanic_auth,
        )
    ).json()

    # The mechanic cannot remove the owner's device…
    denied = await client.delete(
        f"/api/v1/push/subscriptions/{owner_row['id']}", headers=mechanic_auth
    )
    assert denied.status_code == 404, denied.text

    # …and does not see it listed either (own devices only).
    mechanic_list = await client.get("/api/v1/push/subscriptions", headers=mechanic_auth)
    assert [row["id"] for row in mechanic_list.json()] == [mechanic_row["id"]]

    # The owner (admin role) can clean up any device in the tenant.
    removed = await client.delete(
        f"/api/v1/push/subscriptions/{mechanic_row['id']}", headers=auth
    )
    assert removed.status_code == 200 and removed.json()["ok"] is True

    own = await client.delete(
        f"/api/v1/push/subscriptions/{owner_row['id']}", headers=auth
    )
    assert own.status_code == 200


async def test_test_send_counts_and_prunes_dead_endpoints(make_workspace, monkeypatch):
    from app.services import push as push_service

    client, slug, _email, token = await make_workspace("pushtest")
    auth = _headers(slug, token)

    await client.post(
        "/api/v1/push/subscriptions",
        json=_subscription(f"https://push.example.com/ep-{slug}-live"),
        headers=auth,
    )
    await client.post(
        "/api/v1/push/subscriptions",
        json=_subscription(f"https://push.example.com/ep-{slug}-gone"),
        headers=auth,
    )

    fake = _FakeWebPush()
    monkeypatch.setattr(push_service, "webpush", fake)

    sent = await client.post("/api/v1/push/test", headers=auth)
    assert sent.status_code == 200, sent.text
    assert sent.json() == {"sent": 1, "failed": 1}
    assert len(fake.calls) == 2

    # The 410 endpoint is pruned from the device list.
    listed = await client.get("/api/v1/push/subscriptions", headers=auth)
    endpoints = [row["endpoint"] for row in listed.json()]
    assert endpoints == [f"https://push.example.com/ep-{slug}-live"]


async def test_booking_request_pushes_managers_not_mechanics(make_workspace, monkeypatch):
    from app.services import push as push_service

    client, slug, _email, token = await make_workspace("pushbkg")
    auth = _headers(slug, token)
    await _create_mechanic(client, slug, token)
    mechanic_auth = await _login(client, slug, f"wrench@{slug}.example", "mechanic-pass-123")

    await client.post(
        "/api/v1/push/subscriptions",
        json=_subscription(f"https://push.example.com/ep-{slug}-owner"),
        headers=auth,
    )
    await client.post(
        "/api/v1/push/subscriptions",
        json=_subscription(f"https://push.example.com/ep-{slug}-mech"),
        headers=mechanic_auth,
    )

    await _upgrade_to_pro(client, auth)
    settings_response = await client.patch(
        "/api/v1/settings/profile",
        json={"booking_enabled": True, "business_hours": {"mon": [["09:00", "17:00"]]}},
        headers=auth,
    )
    assert settings_response.status_code == 200, settings_response.text
    page = await client.get(f"/api/v1/public/booking/{slug}")
    slots = [slot for slot in page.json()["slots"] if slot["available"]]
    assert slots

    fake = _FakeWebPush()
    monkeypatch.setattr(push_service, "webpush", fake)

    submitted = await client.post(
        f"/api/v1/public/booking/{slug}",
        json={
            "name": "Nadia Karam",
            "phone": "+15550199",
            "plate_number": "bkg123",
            "make": "Kia",
            "model": "Sportage",
            "year": 2021,
            "service_description": "AC not cooling",
            "preferred_at": slots[0]["start"],
        },
    )
    assert submitted.status_code == 201, submitted.text

    assert fake.calls == [f"https://push.example.com/ep-{slug}-owner"]


async def test_order_assignment_pushes_the_mechanic(make_workspace, monkeypatch):
    from app.services import push as push_service

    from test_api_flow import _create_customer, _create_vehicle

    client, slug, _email, token = await make_workspace("pushord")
    auth = _headers(slug, token)
    mechanic = await _create_mechanic(client, slug, token)
    mechanic_auth = await _login(client, slug, f"wrench@{slug}.example", "mechanic-pass-123")
    await client.post(
        "/api/v1/push/subscriptions",
        json=_subscription(f"https://push.example.com/ep-{slug}-mech"),
        headers=mechanic_auth,
    )

    customer = await _create_customer(client, slug, token)
    vehicle = await _create_vehicle(client, slug, token, customer["id"])

    fake = _FakeWebPush()
    monkeypatch.setattr(push_service, "webpush", fake)

    created = await client.post(
        "/api/v1/service-orders",
        json={
            "vehicle_id": vehicle["id"],
            "description": "Assigned at creation",
            "mechanic_id": mechanic["id"],
        },
        headers=auth,
    )
    assert created.status_code == 201, created.text
    order = created.json()
    assert fake.calls == [f"https://push.example.com/ep-{slug}-mech"]

    # Re-saving without changing the mechanic does not re-ping…
    fake.calls.clear()
    untouched = await client.patch(
        f"/api/v1/service-orders/{order['id']}",
        json={"mechanic_id": mechanic["id"]},
        headers=auth,
    )
    assert untouched.status_code == 200
    assert fake.calls == []

    # …but a real reassignment does.
    staff = await client.get("/api/v1/staff", headers=auth)
    staff_rows = staff.json()
    if isinstance(staff_rows, dict):
        staff_rows = staff_rows["items"]
    owner = next(row for row in staff_rows if row["role"] == "owner")
    await client.post(
        "/api/v1/push/subscriptions",
        json=_subscription(f"https://push.example.com/ep-{slug}-owner"),
        headers=auth,
    )
    reassigned = await client.patch(
        f"/api/v1/service-orders/{order['id']}",
        json={"mechanic_id": owner["id"]},
        headers=auth,
    )
    assert reassigned.status_code == 200, reassigned.text
    assert fake.calls == [f"https://push.example.com/ep-{slug}-owner"]
