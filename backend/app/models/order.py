from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    part_items: Mapped[list["OrderPartItem"]] = relationship("OrderPartItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    bom_version_id: Mapped[int | None] = mapped_column(ForeignKey("device_bom_versions.id", ondelete="SET NULL"), nullable=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("order_id", "device_id", name="uq_order_items_order_device"),)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    device: Mapped["Device"] = relationship("Device", foreign_keys=[device_id])
    bom_version: Mapped["DeviceBomVersion | None"] = relationship("DeviceBomVersion", foreign_keys=[bom_version_id])
