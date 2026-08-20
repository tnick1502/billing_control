from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InventoryDocument(Base):
    """Проведённая инвентаризация за календарный месяц.

    Документ привязан к месяцу, а не к ревизии месячного плана: пересоздание плана
    не должно удалять уже зафиксированные физические остатки.
    """

    __tablename__ = "inventory_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="posted")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("month", name="uq_inventory_documents_month"),
        CheckConstraint("status IN ('posted', 'cancelled')", name="ck_inventory_documents_status"),
        CheckConstraint(
            "month = date_trunc('month', month)::date",
            name="ck_inventory_documents_month_start",
        ).ddl_if(dialect="postgresql"),
    )

    items: Mapped[list["InventoryItem"]] = relationship(
        "InventoryItem", back_populates="document", cascade="all, delete-orphan"
    )


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    inventory_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_documents.id", ondelete="CASCADE"), nullable=False
    )
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="RESTRICT"), nullable=False)
    qty_found: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("inventory_id", "part_id", name="uq_inventory_items_inventory_part"),
        CheckConstraint("qty_found > 0", name="ck_inventory_items_qty_found_positive"),
    )

    document: Mapped["InventoryDocument"] = relationship("InventoryDocument", back_populates="items")
    part: Mapped["Part"] = relationship("Part", foreign_keys=[part_id])
    allocations: Mapped[list["InventoryPlanAllocation"]] = relationship(
        "InventoryPlanAllocation", back_populates="inventory_item", cascade="all, delete-orphan"
    )


class InventoryPlanAllocation(Base):
    """Производное распределение найденного количества на строку плана.

    Таблица полностью пересобирается вместе с переносами остатков. Пользователь её
    напрямую не редактирует; благодаря отдельному источнику инвентаризация не
    превращается в фиктивный счёт и не учитывается дважды.
    """

    __tablename__ = "inventory_plan_allocations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    inventory_item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("monthly_plans.id", ondelete="CASCADE"), nullable=False
    )
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"), nullable=False)
    qty_covered: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "inventory_item_id",
            "plan_id",
            "part_id",
            name="uq_inventory_plan_allocations_source_plan_part",
        ),
        CheckConstraint("qty_covered > 0", name="ck_inventory_plan_allocations_qty_positive"),
    )

    inventory_item: Mapped["InventoryItem"] = relationship("InventoryItem", back_populates="allocations")
    plan: Mapped["MonthlyPlan"] = relationship("MonthlyPlan")
    part: Mapped["Part"] = relationship("Part", foreign_keys=[part_id])
