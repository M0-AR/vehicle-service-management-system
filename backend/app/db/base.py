from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def uuid_pk() -> Mapped[uuid.UUID]:
    from sqlalchemy.orm import mapped_column as mc

    return mc(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


def created_at_col() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


def updated_at_col() -> Mapped[datetime]:
    # Python-side onupdate: the new value is set in-process during flush, so
    # the attribute is never expired and post-update serialization cannot
    # trigger a lazy load (MissingGreenlet) under asyncpg.
    return mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=now,
        nullable=False,
    )
