"""Parts supplier catalog providers.

V1 ships two keyless providers behind one interface (the seam partner APIs can
be added to later):

- ``stub`` — a small built-in distributor catalog for dev, tests and demos.
- ``csv``  — a tenant-uploaded distributor price list.

Both normalize to the same offer shape and can feed the inventory importer.
"""

from __future__ import annotations

import csv
import io
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Part
from app.models.supplier import SupplierCatalogItem, SupplierConnection
from app.schemas.supplier import CatalogImportResult, OfferOut

MAX_CATALOG_BYTES = 2_000_000
MAX_CATALOG_ROWS = 5_000
MAX_SEARCH_RESULTS = 50
REQUIRED_COLUMNS = ("sku", "description")

STUB_CATALOG: tuple[dict[str, object], ...] = (
    {
        "sku": "BP-3221",
        "brand": "Bosch",
        "description": "Front brake pad set, ceramic",
        "cost": Decimal("38.40"),
        "price": Decimal("64.99"),
        "stock_qty": Decimal("24"),
    },
    {
        "sku": "BD-1180",
        "brand": "Brembo",
        "description": "Front brake disc, ventilated 280mm",
        "cost": Decimal("52.10"),
        "price": Decimal("89.50"),
        "stock_qty": Decimal("12"),
    },
    {
        "sku": "OF-5512",
        "brand": "Mann",
        "description": "Oil filter, spin-on",
        "cost": Decimal("6.25"),
        "price": Decimal("12.40"),
        "stock_qty": Decimal("80"),
    },
    {
        "sku": "AF-7740",
        "brand": "Mann",
        "description": "Air filter panel",
        "cost": Decimal("11.80"),
        "price": Decimal("21.90"),
        "stock_qty": Decimal("46"),
    },
    {
        "sku": "CF-2209",
        "brand": "Mahle",
        "description": "Cabin filter, activated carbon",
        "cost": Decimal("9.40"),
        "price": Decimal("18.75"),
        "stock_qty": Decimal("33"),
    },
    {
        "sku": "SP-4417",
        "brand": "NGK",
        "description": "Iridium spark plug (single)",
        "cost": Decimal("8.90"),
        "price": Decimal("16.50"),
        "stock_qty": Decimal("120"),
    },
    {
        "sku": "WB-6030",
        "brand": "Bosch",
        "description": 'Wiper blade 24"',
        "cost": Decimal("7.15"),
        "price": Decimal("14.99"),
        "stock_qty": Decimal("58"),
    },
    {
        "sku": "BAT-70A",
        "brand": "Varta",
        "description": "Battery 70Ah 630A",
        "cost": Decimal("74.00"),
        "price": Decimal("119.00"),
        "stock_qty": Decimal("9"),
    },
    {
        "sku": "ALT-1450",
        "brand": "Valeo",
        "description": "Alternator 120A remanufactured",
        "cost": Decimal("148.00"),
        "price": Decimal("235.00"),
        "stock_qty": Decimal("4"),
    },
    {
        "sku": "TB-8890",
        "brand": "Gates",
        "description": "Timing belt kit",
        "cost": Decimal("61.20"),
        "price": Decimal("104.00"),
        "stock_qty": Decimal("7"),
    },
    {
        "sku": "COOL-G12",
        "brand": "Febi",
        "description": "Coolant G12 concentrate 5L",
        "cost": Decimal("13.60"),
        "price": Decimal("24.50"),
        "stock_qty": Decimal("22"),
    },
    {
        "sku": "SHK-3310",
        "brand": "KYB",
        "description": "Rear shock absorber, gas",
        "cost": Decimal("44.80"),
        "price": Decimal("79.90"),
        "stock_qty": Decimal("10"),
    },
)


class CatalogCsvError(ValueError):
    pass


def _stub_offers(connection: SupplierConnection, needle: str) -> list[OfferOut]:
    offers: list[OfferOut] = []
    for item in STUB_CATALOG:
        haystack = " ".join(
            str(item[key]) for key in ("sku", "brand", "description")
        ).lower()
        if needle in haystack:
            offers.append(
                OfferOut(
                    connection_id=connection.id,
                    supplier=connection.name,
                    sku=str(item["sku"]),
                    brand=str(item["brand"]),
                    description=str(item["description"]),
                    cost=item["cost"],
                    price=item["price"],
                    stock_qty=item["stock_qty"],
                    portal_url=connection.portal_url,
                )
            )
    return offers


def _item_offer(
    connection: SupplierConnection, item: SupplierCatalogItem
) -> OfferOut:
    return OfferOut(
        connection_id=connection.id,
        supplier=connection.name,
        sku=item.sku,
        brand=item.brand,
        description=item.description,
        cost=item.cost,
        price=item.price,
        stock_qty=item.stock_qty,
        portal_url=connection.portal_url,
    )


async def search(
    session: AsyncSession,
    connections: list[SupplierConnection],
    q: str,
    limit: int = 20,
) -> list[OfferOut]:
    needle = q.strip().lower()
    if not needle:
        return []
    limit = max(1, min(limit, MAX_SEARCH_RESULTS))
    offers: list[OfferOut] = []

    csv_ids = [c.id for c in connections if c.provider == "csv"]
    grouped: dict[uuid.UUID, list[SupplierCatalogItem]] = {}
    if csv_ids:
        pattern = f"%{needle}%"
        rows = (
            await session.scalars(
                select(SupplierCatalogItem).where(
                    SupplierCatalogItem.connection_id.in_(csv_ids),
                    or_(
                        SupplierCatalogItem.sku.ilike(pattern),
                        SupplierCatalogItem.description.ilike(pattern),
                        SupplierCatalogItem.brand.ilike(pattern),
                    ),
                )
            )
        ).all()
        for item in rows:
            grouped.setdefault(item.connection_id, []).append(item)

    for connection in connections:
        if connection.provider == "csv":
            offers.extend(
                _item_offer(connection, item)
                for item in grouped.get(connection.id, [])
            )
        else:
            offers.extend(_stub_offers(connection, needle))

    offers.sort(key=lambda offer: (offer.price, offer.supplier, offer.sku))
    return offers[:limit]


async def resolve_offer(
    session: AsyncSession, connection: SupplierConnection, sku: str
) -> OfferOut | None:
    wanted = sku.strip()
    if connection.provider == "csv":
        item = await session.scalar(
            select(SupplierCatalogItem).where(
                SupplierCatalogItem.connection_id == connection.id,
                func.lower(SupplierCatalogItem.sku) == wanted.lower(),
            )
        )
        return _item_offer(connection, item) if item else None
    for item in STUB_CATALOG:
        if str(item["sku"]).lower() == wanted.lower():
            return OfferOut(
                connection_id=connection.id,
                supplier=connection.name,
                sku=str(item["sku"]),
                brand=str(item["brand"]),
                description=str(item["description"]),
                cost=item["cost"],
                price=item["price"],
                stock_qty=item["stock_qty"],
                portal_url=connection.portal_url,
            )
    return None


async def import_offer(
    session: AsyncSession,
    connection: SupplierConnection,
    offer: OfferOut,
) -> tuple[Part, bool]:
    part = await session.scalar(
        select(Part).where(
            Part.tenant_id == connection.tenant_id,
            Part.sku == offer.sku,
        )
    )
    created = part is None
    if part is None:
        part = Part(
            tenant_id=connection.tenant_id,
            sku=offer.sku,
            name=offer.description[:160],
            brand=offer.brand,
            supplier=connection.name,
            cost=offer.cost,
            price=offer.price,
            stock_qty=Decimal("0"),
        )
        session.add(part)
    else:
        part.name = offer.description[:160]
        part.brand = offer.brand
        part.supplier = connection.name
        part.cost = offer.cost
        part.price = offer.price
    await session.flush()
    return part, created


def parse_catalog_csv(raw: bytes) -> tuple[list[dict[str, object]], int]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CatalogCsvError("CSV must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise CatalogCsvError("CSV needs a header row: sku,description")
    reader.fieldnames = [str(name).strip().lower() for name in reader.fieldnames]
    missing = [name for name in REQUIRED_COLUMNS if name not in reader.fieldnames]
    if missing:
        raise CatalogCsvError(
            "CSV is missing required column(s): " + ", ".join(missing)
        )

    rows: list[dict[str, object]] = []
    skipped = 0
    for index, row in enumerate(reader, start=2):
        if index > MAX_CATALOG_ROWS + 1:
            raise CatalogCsvError(
                f"CSV is limited to {MAX_CATALOG_ROWS} data rows"
            )
        sku = (row.get("sku") or "").strip()
        description = (row.get("description") or "").strip()
        if not sku or not description:
            skipped += 1
            continue
        if len(sku) > 80 or len(description) > 240:
            skipped += 1
            continue
        values: dict[str, Decimal] = {}
        valid = True
        for field in ("cost", "price", "stock"):
            raw_value = (row.get(field) or "0").strip() or "0"
            try:
                value = Decimal(raw_value)
            except InvalidOperation:
                valid = False
                break
            if value < 0:
                valid = False
                break
            values[field] = value
        if not valid:
            skipped += 1
            continue
        brand = (row.get("brand") or "").strip() or None
        rows.append(
            {
                "sku": sku,
                "brand": brand[:80] if brand else None,
                "description": description,
                "cost": values["cost"],
                "price": values["price"],
                "stock_qty": values["stock"],
            }
        )
    return rows, skipped


async def import_catalog(
    session: AsyncSession,
    connection: SupplierConnection,
    rows: list[dict[str, object]],
) -> CatalogImportResult:
    skus = [str(row["sku"]) for row in rows]
    existing = {}
    if skus:
        existing = {
            item.sku: item
            for item in (
                await session.scalars(
                    select(SupplierCatalogItem).where(
                        SupplierCatalogItem.connection_id == connection.id,
                        SupplierCatalogItem.sku.in_(skus),
                    )
                )
            ).all()
        }
    imported = 0
    updated = 0
    for row in rows:
        sku = str(row["sku"])
        item = existing.get(sku)
        if item is None:
            item = SupplierCatalogItem(
                tenant_id=connection.tenant_id,
                connection_id=connection.id,
                sku=sku,
                brand=row["brand"],
                description=str(row["description"]),
                cost=row["cost"],
                price=row["price"],
                stock_qty=row["stock_qty"],
            )
            session.add(item)
            imported += 1
        else:
            item.brand = row["brand"]
            item.description = str(row["description"])
            item.cost = row["cost"]
            item.price = row["price"]
            item.stock_qty = row["stock_qty"]
            updated += 1
    await session.flush()
    return CatalogImportResult(
        imported=imported, updated=updated, skipped=0
    )
