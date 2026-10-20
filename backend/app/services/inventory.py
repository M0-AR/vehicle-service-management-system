"""Stock helpers shared by the inventory router and order line items.

Quantities are Decimal-backed Numeric columns; every change is recorded as a
`stock_movements` row so the ledger can be audited or replayed.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Part, StockMovement


def _qty(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


async def record_movement(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    part: Part,
    delta: Decimal,
    reason: str,
    note: str | None = None,
    order_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> StockMovement:
    delta = _qty(delta)
    new_qty = _qty(part.stock_qty) + delta
    if new_qty < 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Only {_qty(part.stock_qty)} of {part.name} in stock"
                f" ({abs(delta)} requested)"
            ),
        )
    part.stock_qty = new_qty
    movement = StockMovement(
        tenant_id=tenant_id,
        part_id=part.id,
        delta=delta,
        reason=reason,
        note=note,
        order_id=order_id,
        user_id=user_id,
    )
    session.add(movement)
    return movement


async def issue_part(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    part: Part,
    quantity: Decimal,
    order_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    note: str | None = None,
) -> StockMovement:
    return await record_movement(
        session,
        tenant_id=tenant_id,
        part=part,
        delta=-_qty(quantity),
        reason="issued",
        note=note,
        order_id=order_id,
        user_id=user_id,
    )


async def return_part(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    part: Part,
    quantity: Decimal,
    order_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    note: str | None = None,
) -> StockMovement:
    return await record_movement(
        session,
        tenant_id=tenant_id,
        part=part,
        delta=_qty(quantity),
        reason="returned",
        note=note,
        order_id=order_id,
        user_id=user_id,
    )
