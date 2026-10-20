from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class DashboardStats(BaseModel):
    vehicles_total: int
    vehicles_in_service: int
    customers_total: int
    orders_open: int
    orders_by_status: dict[str, int]
    revenue_mtd: Decimal
    revenue_30d: Decimal
    unpaid_total: Decimal
    unpaid_count: int
    upcoming: list[dict]
    recent_orders: list[dict]
