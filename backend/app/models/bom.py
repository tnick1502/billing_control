from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DeviceBomVersion(Base):
    __tablename__ = "device_bom_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("device_id", "version", name="uq_device_bom_versions_device_version"),)

    device: Mapped["Device"] = relationship("Device", foreign_keys=[device_id])
    items: Mapped[list["DeviceBomItem"]] = relationship("DeviceBomItem", back_populates="bom_version", cascade="all, delete-orphan")


class DeviceBomItem(Base):
    __tablename__ = "device_bom_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    bom_version_id: Mapped[int] = mapped_column(ForeignKey("device_bom_versions.id", ondelete="CASCADE"), nullable=False)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"), nullable=False)
    qty_per_device: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    scrap_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("bom_version_id", "part_id", name="uq_device_bom_items_bom_part"),)

    bom_version: Mapped["DeviceBomVersion"] = relationship("DeviceBomVersion", back_populates="items")
    part: Mapped["Part"] = relationship("Part", foreign_keys=[part_id])
