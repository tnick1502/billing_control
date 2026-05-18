from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DeviceBomVersion(Base):
    __tablename__ = "device_bom_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    # Exactly one of part_id / sub_device_id must be set (enforced at API level)
    part_id: Mapped[int | None] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"), nullable=True)
    sub_device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=True)
    sub_bom_version_id: Mapped[int | None] = mapped_column(ForeignKey("device_bom_versions.id", ondelete="SET NULL"), nullable=True)
    qty_per_device: Mapped[int] = mapped_column(Integer, nullable=False)
    scrap_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # PostgreSQL treats NULLs as distinct in UNIQUE constraints,
        # so multiple sub-device rows (part_id=NULL) don't conflict, and vice versa.
        UniqueConstraint("bom_version_id", "part_id", name="uq_device_bom_items_bom_part"),
        UniqueConstraint("bom_version_id", "sub_device_id", name="uq_device_bom_items_bom_subdev"),
    )

    bom_version: Mapped["DeviceBomVersion"] = relationship(
        "DeviceBomVersion", back_populates="items", foreign_keys=[bom_version_id]
    )
    part: Mapped["Part | None"] = relationship("Part", foreign_keys=[part_id])
    sub_device: Mapped["Device | None"] = relationship("Device", foreign_keys=[sub_device_id])
    sub_bom_version: Mapped["DeviceBomVersion | None"] = relationship(
        "DeviceBomVersion", foreign_keys=[sub_bom_version_id]
    )

    @property
    def item_type(self) -> str:
        return "sub_device" if self.sub_device_id is not None else "part"
