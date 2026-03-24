from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MonthlyPlan(Base):
    __tablename__ = "monthly_plans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    generated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("month", "revision", name="uq_monthly_plans_month_revision"),)

    devices: Mapped[list["MonthlyPlanDevice"]] = relationship("MonthlyPlanDevice", back_populates="plan", cascade="all, delete-orphan")
    parts: Mapped[list["MonthlyPlanPart"]] = relationship("MonthlyPlanPart", back_populates="plan", cascade="all, delete-orphan")


class MonthlyPlanDevice(Base):
    __tablename__ = "monthly_plan_devices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("monthly_plans.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    qty_total: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    bom_version_id: Mapped[int] = mapped_column(ForeignKey("device_bom_versions.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("plan_id", "device_id", "bom_version_id", name="uq_monthly_plan_devices_plan_device_bom"),)

    plan: Mapped["MonthlyPlan"] = relationship("MonthlyPlan", back_populates="devices")
    device: Mapped["Device"] = relationship("Device", foreign_keys=[device_id])
    bom_version: Mapped["DeviceBomVersion"] = relationship("DeviceBomVersion", foreign_keys=[bom_version_id])


class MonthlyPlanPart(Base):
    __tablename__ = "monthly_plan_parts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("monthly_plans.id", ondelete="CASCADE"), nullable=False)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"), nullable=False)
    qty_required: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    qty_final: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    qty_delivered: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("plan_id", "part_id", name="uq_monthly_plan_parts_plan_part"),)

    plan: Mapped["MonthlyPlan"] = relationship("MonthlyPlan", back_populates="parts")
    part: Mapped["Part"] = relationship("Part", foreign_keys=[part_id])
    files: Mapped[list["MonthlyPlanPartFile"]] = relationship(
        "MonthlyPlanPartFile", back_populates="plan_part", cascade="all, delete-orphan"
    )


class MonthlyPlanPartFile(Base):
    __tablename__ = "monthly_plan_part_files"

    plan_part_id: Mapped[int] = mapped_column(ForeignKey("monthly_plan_parts.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    plan_part: Mapped["MonthlyPlanPart"] = relationship("MonthlyPlanPart", back_populates="files")
    file: Mapped["File"] = relationship("File")
