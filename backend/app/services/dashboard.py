from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

OPEN_STATUSES = ("scheduled", "in_progress", "awaiting_parts")


async def stats(session: AsyncSession) -> dict:
    async def scalar(sql: str, **params):
        result = await session.execute(text(sql), params)
        return result.scalar()

    vehicles_total = await scalar("SELECT count(*) FROM vehicles")
    vehicles_in_service = await scalar(
        "SELECT count(*) FROM vehicles WHERE status = 'in_service'"
    )
    customers_total = await scalar("SELECT count(*) FROM customers")
    orders_open = await scalar(
        "SELECT count(*) FROM service_orders WHERE status = ANY(:statuses)",
        statuses=list(OPEN_STATUSES),
    )

    by_status_rows = await session.execute(
        text(
            "SELECT status, count(*) AS n FROM service_orders GROUP BY status"
        )
    )
    orders_by_status = {r["status"]: int(r["n"]) for r in by_status_rows.mappings()}

    revenue_mtd = await scalar(
        "SELECT coalesce(sum(total), 0) FROM invoices"
        " WHERE status = 'paid' AND paid_at >= date_trunc('month', now())"
    )
    revenue_30d = await scalar(
        "SELECT coalesce(sum(total), 0) FROM invoices"
        " WHERE status = 'paid' AND paid_at >= now() - interval '30 days'"
    )
    unpaid_total = await scalar(
        "SELECT coalesce(sum(total), 0) FROM invoices"
        " WHERE status IN ('sent', 'overdue')"
    )
    unpaid_count = await scalar(
        "SELECT count(*) FROM invoices WHERE status IN ('sent', 'overdue')"
    )

    upcoming_rows = await session.execute(
        text(
            """
            SELECT o.id, o.number, o.status, o.priority, o.scheduled_at,
                   v.plate_number, c.name AS customer_name
            FROM service_orders o
            JOIN vehicles v ON v.id = o.vehicle_id
            LEFT JOIN customers c ON c.id = o.customer_id
            WHERE o.scheduled_at >= now() - interval '1 day'
              AND o.status NOT IN ('completed', 'invoiced', 'cancelled')
            ORDER BY o.scheduled_at ASC
            LIMIT 6
            """
        )
    )
    upcoming = [
        {
            "id": str(r["id"]),
            "number": r["number"],
            "status": r["status"],
            "priority": r["priority"],
            "scheduled_at": str(r["scheduled_at"]) if r["scheduled_at"] else None,
            "vehicle_plate": r["plate_number"],
            "customer_name": r["customer_name"],
        }
        for r in upcoming_rows.mappings()
    ]

    recent_rows = await session.execute(
        text(
            """
            SELECT o.id, o.number, o.status, o.created_at,
                   v.plate_number, c.name AS customer_name,
                   coalesce((
                       SELECT sum(i.quantity * i.unit_price)
                       FROM service_items i WHERE i.order_id = o.id
                   ), 0) AS total
            FROM service_orders o
            JOIN vehicles v ON v.id = o.vehicle_id
            LEFT JOIN customers c ON c.id = o.customer_id
            ORDER BY o.created_at DESC
            LIMIT 6
            """
        )
    )
    recent = [
        {
            "id": str(r["id"]),
            "number": r["number"],
            "status": r["status"],
            "created_at": str(r["created_at"]),
            "vehicle_plate": r["plate_number"],
            "customer_name": r["customer_name"],
            "total": str(r["total"]),
        }
        for r in recent_rows.mappings()
    ]

    return {
        "vehicles_total": int(vehicles_total or 0),
        "vehicles_in_service": int(vehicles_in_service or 0),
        "customers_total": int(customers_total or 0),
        "orders_open": int(orders_open or 0),
        "orders_by_status": orders_by_status,
        "revenue_mtd": revenue_mtd or 0,
        "revenue_30d": revenue_30d or 0,
        "unpaid_total": unpaid_total or 0,
        "unpaid_count": int(unpaid_count or 0),
        "upcoming": upcoming,
        "recent_orders": recent,
    }
