"""Public online booking: slot generation + conversion into a service order.

Slots are hourly, 09:00-17:00 by default, on days the tenant opens. Capacity is
two bookings per slot. Existing scheduled/in-progress orders at the same hour
count against capacity. Times are computed in the tenant timezone and returned
with their UTC offset; storage is UTC-aware.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_HOURS = {"mon", "tue", "wed", "thu", "fri"}
DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
SLOT_CAPACITY = 2


def slot_label(moment: datetime) -> str:
    """Human-friendly slot label, e.g. `Mon 19 Oct, 9:00 AM`."""
    return f"{moment:%a %d %b}, {moment.strftime('%I:%M %p').lstrip('0')}"


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _open_days(business_hours: dict | None) -> set[str]:
    if not business_hours:
        return set(DEFAULT_HOURS)
    days = {
        key
        for key, ranges in business_hours.items()
        if key in DAY_KEYS and isinstance(ranges, list) and ranges
    }
    return days or set(DEFAULT_HOURS)


def _hours_for(business_hours: dict | None, day: str) -> list[tuple[time, time]]:
    ranges = (business_hours or {}).get(day) or [["09:00", "17:00"]]
    parsed: list[tuple[time, time]] = []
    for entry in ranges:
        try:
            start, end = entry
            parsed.append(
                (time.fromisoformat(str(start)), time.fromisoformat(str(end)))
            )
        except (ValueError, TypeError):
            continue
    return parsed or [(time(9), time(17))]


async def available_slots(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    timezone_name: str,
    business_hours: dict | None,
    days: int = 14,
) -> list[dict]:
    tz = _zone(timezone_name)
    now_local = datetime.now(tz)
    open_days = _open_days(business_hours)

    # Count existing bookings per hour (open orders only).
    rows = await session.execute(
        text(
            """
            SELECT date_trunc('hour', scheduled_at) AS slot, count(*) AS n
              FROM service_orders
             WHERE tenant_id = :t
               AND status IN ('scheduled', 'in_progress', 'awaiting_parts')
               AND scheduled_at IS NOT NULL
               AND scheduled_at >= :from AND scheduled_at < :to
             GROUP BY 1
            """
        ),
        {
            "t": tenant_id,
            "from": now_local.astimezone(timezone.utc),
            "to": (now_local + timedelta(days=days)).astimezone(timezone.utc),
        },
    )
    taken = {
        row["slot"].astimezone(timezone.utc): int(row["n"]) for row in rows.mappings()
    }

    slots: list[dict] = []
    for offset in range(days + 1):
        day = (now_local + timedelta(days=offset)).date()
        key = DAY_KEYS[day.weekday()]
        if key not in open_days:
            continue
        for start_t, end_t in _hours_for(business_hours, key):
            cursor = datetime.combine(day, start_t, tzinfo=tz)
            close = datetime.combine(day, end_t, tzinfo=tz)
            while cursor + timedelta(hours=1) <= close:
                if cursor > now_local + timedelta(hours=2):
                    utc = cursor.astimezone(timezone.utc)
                    used = taken.get(utc, 0)
                    slots.append(
                        {
                            "start": cursor,
                            "label": slot_label(cursor),
                            "available": used < SLOT_CAPACITY,
                        }
                    )
                cursor += timedelta(hours=1)
    return slots


def parse_slot(value: datetime, timezone_name: str) -> datetime:
    """Normalize a requested slot to a UTC-aware datetime on the hour."""
    tz = _zone(timezone_name)
    if value.tzinfo is None:
        value = value.replace(tzinfo=tz)
    return value.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


async def slot_is_available(
    session: AsyncSession, tenant_id: uuid.UUID, slot_utc: datetime
) -> bool:
    count = await session.scalar(
        text(
            """
            SELECT count(*) FROM service_orders
             WHERE tenant_id = :t
               AND status IN ('scheduled', 'in_progress', 'awaiting_parts')
               AND scheduled_at >= :start AND scheduled_at < :end
            """
        ),
        {
            "t": tenant_id,
            "start": slot_utc,
            "end": slot_utc + timedelta(hours=1),
        },
    )
    return int(count or 0) < SLOT_CAPACITY
