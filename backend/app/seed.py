"""Demo data seeding — `python -m app.seed` (or `make seed`).

Idempotent: refuses to run if the demo workspace exists unless FORCE_SEED=1.
Runs entirely through the application role (app_user) so seeded data proves
the RLS path end to end.
"""

from __future__ import annotations

import asyncio
import os
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text

from app.core.config import get_settings
from app.core.security import hash_password
from app.core.tenancy import set_rls_context
from app.db.session import SessionLocal
from app.models.customer import Customer
from app.models.tenant import DEFAULT_BRAND, Tenant, TenantSettings
from app.models.user import User
from app.services import audit
from app.services.numbering import next_number

settings = get_settings()
random.seed(42)

DEMO_SLUG = "demo"
OWNER_EMAIL = "owner@demo.example"
OWNER_PASSWORD = os.environ.get("SEED_PASSWORD", "demo-password-123")

CUSTOMERS = [
    ("Sara Haddad", "sara.haddad@example.com", "+1-555-0101", "12 Cedar Ave"),
    ("James Okafor", "james.okafor@example.com", "+1-555-0102", "89 Maple St"),
    ("Lena Petrova", "lena.petrova@example.com", "+1-555-0103", "5 Birch Rd"),
    ("Ahmed Karim", "ahmed.karim@example.com", "+1-555-0104", "203 Oak Blvd"),
    ("Mia Chen", "mia.chen@example.com", "+1-555-0105", "77 Elm Ln"),
    ("Tomás Rivera", "tomas.rivera@example.com", "+1-555-0106", "31 Pine Ct"),
    ("Priya Nair", "priya.nair@example.com", "+1-555-0107", "14 Aspen Way"),
    ("Daniel Berg", "daniel.berg@example.com", "+1-555-0108", "9 Willow Dr"),
]

VEHICLES = [
    ("AB-1234", "Toyota", "Corolla", 2019, "petrol"),
    ("CD-5678", "Honda", "Civic", 2021, "petrol"),
    ("EF-9012", "Tesla", "Model 3", 2022, "electric"),
    ("GH-3456", "Ford", "Transit", 2018, "diesel"),
    ("IJ-7890", "BMW", "320i", 2020, "petrol"),
    ("KL-2345", "Toyota", "Prius", 2021, "hybrid"),
    ("MN-6789", "Nissan", "Leaf", 2020, "electric"),
    ("OP-1122", "Hyundai", "Tucson", 2022, "diesel"),
    ("QR-3344", "Volkswagen", "Golf", 2017, "petrol"),
    ("ST-5566", "Kia", "Sportage", 2023, "hybrid"),
    ("UV-7788", "Mercedes", "Sprinter", 2019, "diesel"),
    ("WX-9900", "Mazda", "CX-5", 2021, "petrol"),
    ("YZ-1357", "Renault", "Zoe", 2020, "electric"),
    ("BC-2468", "Subaru", "Outback", 2018, "petrol"),
]

WORK_ITEMS = {
    "Oil & filter service": [("labor", "Oil change", 0.5, 45), ("part", "Oil filter", 1, 12), ("part", "Engine oil 5W-30", 4, 8.5)],
    "Brake pads replacement": [("labor", "Brake service", 2, 45), ("part", "Front brake pads", 1, 65), ("part", "Brake fluid", 1, 15)],
    "Battery replacement": [("labor", "Battery swap", 0.5, 45), ("part", "12V battery", 1, 130)],
    "Tire rotation & alignment": [("labor", "Rotation & alignment", 1.5, 55), ("part", "Wheel weights", 1, 6)],
    "Air conditioning service": [("labor", "A/C service", 1.5, 60), ("part", "A/C refrigerant", 1, 25)],
    "Full inspection": [("labor", "Inspection", 1, 50)],
    "Timing belt replacement": [("labor", "Timing belt job", 4, 55), ("part", "Timing belt kit", 1, 180)],
    "Suspension repair": [("labor", "Suspension work", 3, 60), ("part", "Strut assembly", 2, 145)],
}


async def seed() -> None:
    async with SessionLocal() as session:
        async with session.begin():
            existing = await session.execute(
                text("SELECT id FROM tenants WHERE slug = :s"), {"s": DEMO_SLUG}
            )
            if existing.scalar_one_or_none() is not None and os.environ.get("FORCE_SEED") != "1":
                print(f"Demo workspace '{DEMO_SLUG}' already exists — skipping (FORCE_SEED=1 to reseed).")
                return

            tenant = Tenant(name="Downtown Auto Care", slug=DEMO_SLUG, plan="pro", region=settings.default_region)
            session.add(tenant)
            await session.flush()
            await set_rls_context(session, tenant.id)

            session.add(
                TenantSettings(
                    tenant_id=tenant.id,
                    currency="USD",
                    timezone="America/New_York",
                    locale="en",
                    tax_rate=Decimal("0.0825"),
                    brand={**DEFAULT_BRAND, "display_name": "Downtown Auto Care"},
                )
            )
            session.add(
                User(
                    tenant_id=tenant.id,
                    email=OWNER_EMAIL,
                    name="Alex Morgan",
                    password_hash=hash_password(OWNER_PASSWORD),
                    role="owner",
                )
            )
            session.add(
                User(
                    tenant_id=tenant.id,
                    email="mike.mechanic@demo.example",
                    name="Mike Torres",
                    password_hash=hash_password(OWNER_PASSWORD),
                    role="mechanic",
                )
            )
            await session.execute(
                text(
                    "INSERT INTO billing_accounts (tenant_id, provider, plan, status)"
                    " VALUES (:t, :p, 'pro', 'active') ON CONFLICT (tenant_id) DO NOTHING"
                ),
                {"t": tenant.id, "p": settings.billing_provider},
            )

            customers: list[Customer] = []
            for name, email, phone, address in CUSTOMERS:
                customer = Customer(
                    tenant_id=tenant.id, name=name, email=email, phone=phone, address=address
                )
                session.add(customer)
                customers.append(customer)
            await session.flush()

            from app.models.vehicle import Vehicle

            vehicles: list[Vehicle] = []
            for index, (plate, make, model, year, fuel) in enumerate(VEHICLES):
                vehicle = Vehicle(
                    tenant_id=tenant.id,
                    customer_id=customers[index % len(customers)].id,
                    plate_number=plate,
                    make=make,
                    model=model,
                    year=year,
                    fuel_type=fuel,
                    mileage=random.randint(8000, 140000),
                )
                session.add(vehicle)
                vehicles.append(vehicle)
            await session.flush()

            from app.models.service import ServiceItem, ServiceOrder

            mechanics = (
                await session.execute(
                    text("SELECT id FROM users WHERE role = 'mechanic' AND tenant_id = :t"),
                    {"t": tenant.id},
                )
            ).scalars().all()

            statuses = ["scheduled", "in_progress", "awaiting_parts", "completed", "completed", "invoiced"]
            now = datetime.now(timezone.utc)
            orders: list[ServiceOrder] = []
            for i, vehicle in enumerate(vehicles):
                job, items = random.choice(list(WORK_ITEMS.items()))
                order_status = statuses[i % len(statuses)]
                order = ServiceOrder(
                    tenant_id=tenant.id,
                    number=await next_number(session, tenant.id, "service_order", "SO"),
                    vehicle_id=vehicle.id,
                    customer_id=vehicle.customer_id,
                    mechanic_id=random.choice(mechanics) if mechanics else None,
                    status=order_status,
                    priority=random.choice(["low", "normal", "normal", "high", "urgent"]),
                    description=job,
                    odometer=vehicle.mileage,
                    scheduled_at=now + timedelta(days=random.randint(-20, 6)),
                    started_at=now - timedelta(days=random.randint(1, 10)) if order_status in ("in_progress", "awaiting_parts", "completed", "invoiced") else None,
                    completed_at=now - timedelta(days=random.randint(0, 5)) if order_status in ("completed", "invoiced") else None,
                )
                session.add(order)
                await session.flush()
                for kind, description, qty, price in items:
                    session.add(
                        ServiceItem(
                            tenant_id=tenant.id,
                            order_id=order.id,
                            kind=kind,
                            description=description,
                            quantity=Decimal(str(qty)),
                            unit_price=Decimal(str(price)),
                        )
                    )
                if order_status == "in_progress":
                    vehicle.status = "in_service"
                orders.append(order)
            await session.flush()

            from app.models.invoice import Invoice

            invoiced = [o for o in orders if o.status == "invoiced"]
            for order in invoiced:
                items_rows = (
                    await session.execute(
                        text(
                            "SELECT kind, description, quantity, unit_price"
                            " FROM service_items WHERE order_id = :o"
                        ),
                        {"o": order.id},
                    )
                ).mappings().all()
                subtotal = sum(
                    (Decimal(str(r["quantity"])) * Decimal(str(r["unit_price"])) for r in items_rows),
                    Decimal("0"),
                )
                tax_rate = Decimal("0.0825")
                tax_amount = (subtotal * tax_rate).quantize(Decimal("0.01"))
                invoice_status = random.choice(["paid", "paid", "sent", "overdue"])
                created = now - timedelta(days=random.randint(1, 20))
                session.add(
                    Invoice(
                        tenant_id=tenant.id,
                        number=await next_number(session, tenant.id, "invoice", "INV"),
                        order_id=order.id,
                        customer_id=order.customer_id,
                        status=invoice_status,
                        issued_at=created,
                        due_at=created + timedelta(days=14),
                        subtotal=subtotal,
                        tax_rate=tax_rate,
                        tax_amount=tax_amount,
                        total=subtotal + tax_amount,
                        currency="USD",
                        paid_at=created + timedelta(days=2) if invoice_status == "paid" else None,
                        lines=[
                            {
                                "kind": r["kind"],
                                "description": r["description"],
                                "quantity": str(r["quantity"]),
                                "unit_price": str(r["unit_price"]),
                                "total": str(Decimal(str(r["quantity"])) * Decimal(str(r["unit_price"]))),
                            }
                            for r in items_rows
                        ],
                        meta={"order_number": order.number, "seeded": True},
                    )
                )

            await audit.record(
                session,
                tenant_id=tenant.id,
                user_id=None,
                action="seed.completed",
                entity="tenant",
                entity_id=tenant.id,
                meta={"customers": len(customers), "vehicles": len(vehicles), "orders": len(orders)},
            )

            scheme = "http" if settings.env == "dev" else "https"
            base = settings.platform_base_domain
            print("Seed complete.")
            print(f"  Workspace: {scheme}://{DEMO_SLUG}.{base}")
            print(f"  Login:     {OWNER_EMAIL} / {OWNER_PASSWORD}")
            print(f"  Data:      {len(customers)} customers, {len(vehicles)} vehicles, {len(orders)} orders")


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
