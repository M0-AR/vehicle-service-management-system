from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col

# Registry table (intentionally RLS-free): public links are resolved before any
# tenant context exists — the token itself is the capability. Holds routing ids
# only (no PII); the actual payload is loaded through tenant-scoped tables once
# the owning tenant_id has been resolved and the RLS context set.

LINK_KINDS = ("order", "estimate")


class PublicLink(Base):
    __tablename__ = "public_links"
    __table_args__ = (Index("ix_public_links_kind_entity", "kind", "entity_id"),)

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
