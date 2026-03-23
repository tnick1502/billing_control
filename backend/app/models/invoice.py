from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_no: Mapped[str] = mapped_column(String(64), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="RUB")
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="received")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("invoice_no", "invoice_date", name="uq_invoices_no_date"),)

    files: Mapped[list["InvoiceFile"]] = relationship("InvoiceFile", back_populates="invoice", cascade="all, delete-orphan")
    part_links: Mapped[list["InvoicePartLink"]] = relationship("InvoicePartLink", back_populates="invoice", cascade="all, delete-orphan")


class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    storage: Mapped[str] = mapped_column(String(16), nullable=False, default="s3")
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    etag: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("bucket", "object_key", name="uq_files_bucket_key"),)


class InvoiceFile(Base):
    __tablename__ = "invoice_files"

    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="original")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="files")
    file: Mapped["File"] = relationship("File")


class InvoicePartLink(Base):
    __tablename__ = "invoice_part_links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("monthly_plans.id", ondelete="CASCADE"), nullable=False)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"), nullable=False)
    qty_covered: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    amount_allocated: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("invoice_id", "plan_id", "part_id", name="uq_invoice_part_links_invoice_plan_part"),)

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="part_links")
    plan: Mapped["MonthlyPlan"] = relationship("MonthlyPlan")
    part: Mapped["Part"] = relationship("Part", foreign_keys=[part_id])
