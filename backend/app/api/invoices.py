from datetime import date
from decimal import Decimal

from decimal import InvalidOperation

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Invoice, File as FileModel, InvoiceFile, InvoicePartLink
from app.schemas.common import (
    InvoiceRead,
    InvoiceUpdate,
    InvoicePartLinkCreate,
    InvoicePartLinkRead,
    InvoicePartLinkUpdate,
    FileRead,
)
from app.services.carryover import recompute_carryover_links
from app.services.file_storage import delete_orphaned_files, save_upload_as_file

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("", response_model=list[InvoiceRead])
async def list_invoices(session: AsyncSession = Depends(get_db, scope="function")):
    result = await session.execute(select(Invoice).order_by(Invoice.invoice_date.desc()))
    return result.scalars().all()


def _clean_invoice_payload(d: dict) -> dict:
    """Пустые строки из форм → None; суммы приводим к Decimal."""
    out = dict(d)
    for key in ("invoice_no", "supplier", "total_amount", "note", "description"):
        if out.get(key) == "":
            out[key] = None
    if isinstance(out.get("invoice_no"), str):
        out["invoice_no"] = out["invoice_no"].strip()
    if out.get("total_amount") is not None:
        try:
            out["total_amount"] = Decimal(str(out["total_amount"]))
        except (ValueError, InvalidOperation):
            raise HTTPException(400, "Некорректная сумма счёта")
    return {k: v for k, v in out.items() if v is not None}


def _parse_invoice_form_dates(
    invoice_no: str,
    invoice_date: str,
    supplier: str | None,
    total_amount: str | None,
    payment_date: str | None,
    description: str | None,
    note: str | None,
) -> dict:
    try:
        idate = date.fromisoformat(invoice_date.strip())
    except ValueError:
        raise HTTPException(400, "Некорректная дата счёта") from None
    pdate: date | None = None
    if payment_date and str(payment_date).strip():
        try:
            pdate = date.fromisoformat(str(payment_date).strip())
        except ValueError:
            raise HTTPException(400, "Некорректная дата оплаты") from None
    raw = {
        "invoice_no": invoice_no,
        "invoice_date": idate,
        "supplier": supplier,
        "total_amount": total_amount,
        "payment_date": pdate,
        "description": description,
        "note": note,
    }
    return _clean_invoice_payload(raw)


@router.post("", response_model=InvoiceRead)
async def create_invoice(
    invoice_no: str = Form(...),
    invoice_date: str = Form(...),
    supplier: str | None = Form(None),
    total_amount: str | None = Form(None),
    payment_date: str | None = Form(None),
    description: str | None = Form(None),
    note: str | None = Form(None),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db, scope="function"),
):
    dump = _parse_invoice_form_dates(
        invoice_no=invoice_no,
        invoice_date=invoice_date,
        supplier=supplier,
        total_amount=total_amount,
        payment_date=payment_date,
        description=description,
        note=note,
    )
    if not dump.get("invoice_no"):
        raise HTTPException(400, "Номер счета обязателен")

    invoice = Invoice(**dump)
    session.add(invoice)
    await session.flush()

    try:
        db_file = await save_upload_as_file(session, file)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    session.add(InvoiceFile(invoice_id=invoice.id, file_id=db_file.id, role="original"))
    await session.flush()
    await session.refresh(invoice)
    return invoice


@router.get("/{invoice_id}", response_model=InvoiceRead)
async def get_invoice(invoice_id: int, session: AsyncSession = Depends(get_db, scope="function")):
    result = await session.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    return invoice


@router.patch("/{invoice_id}", response_model=InvoiceRead)
async def update_invoice(invoice_id: int, data: InvoiceUpdate, session: AsyncSession = Depends(get_db, scope="function")):
    result = await session.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    update_data = data.model_dump(exclude_unset=True)
    for key in ("invoice_no", "supplier", "total_amount", "note", "description"):
        if update_data.get(key) == "":
            update_data[key] = None
    if isinstance(update_data.get("invoice_no"), str):
        update_data["invoice_no"] = update_data["invoice_no"].strip()
    if "invoice_no" in update_data and not update_data["invoice_no"]:
        raise HTTPException(400, "Номер счета обязателен")
    for k, v in update_data.items():
        setattr(invoice, k, v)
    await session.flush()
    await session.refresh(invoice)
    return invoice


@router.delete("/{invoice_id}", status_code=204)
async def delete_invoice(invoice_id: int, session: AsyncSession = Depends(get_db, scope="function")):
    result = await session.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    linked = await session.execute(select(InvoiceFile.file_id).where(InvoiceFile.invoice_id == invoice_id))
    file_ids = list(linked.scalars().all())
    await session.delete(invoice)
    await session.flush()
    await recompute_carryover_links(session)
    await delete_orphaned_files(session, file_ids)
    return None


@router.get("/{invoice_id}/files", response_model=list[FileRead])
async def list_invoice_files(invoice_id: int, session: AsyncSession = Depends(get_db, scope="function")):
    if not await session.get(Invoice, invoice_id):
        raise HTTPException(404, "Invoice not found")
    result = await session.execute(
        select(FileModel)
        .join(InvoiceFile, InvoiceFile.file_id == FileModel.id)
        .where(InvoiceFile.invoice_id == invoice_id)
    )
    return list(result.scalars().all())


@router.post("/{invoice_id}/upload", response_model=FileRead)
async def upload_invoice_file(
    invoice_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db, scope="function"),
):
    result = await session.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "Invoice not found")

    try:
        db_file = await save_upload_as_file(session, file)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    session.add(InvoiceFile(invoice_id=invoice_id, file_id=db_file.id, role="original"))
    await session.flush()
    await session.refresh(db_file)
    return db_file


@router.get("/{invoice_id}/parts", response_model=list[InvoicePartLinkRead])
async def list_invoice_parts(invoice_id: int, session: AsyncSession = Depends(get_db, scope="function")):
    if not await session.get(Invoice, invoice_id):
        raise HTTPException(404, "Invoice not found")
    result = await session.execute(select(InvoicePartLink).where(InvoicePartLink.invoice_id == invoice_id))
    return result.scalars().all()


@router.post("/{invoice_id}/parts", response_model=InvoicePartLinkRead)
async def create_invoice_part_link(
    invoice_id: int,
    data: InvoicePartLinkCreate,
    session: AsyncSession = Depends(get_db, scope="function"),
):
    result = await session.execute(select(Invoice).where(Invoice.id == invoice_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Invoice not found")
    link = InvoicePartLink(invoice_id=invoice_id, is_carryover=False, **data.model_dump())
    session.add(link)
    await session.flush()
    await recompute_carryover_links(session)
    await session.refresh(link)
    return link


@router.patch("/{invoice_id}/parts/{link_id}", response_model=InvoicePartLinkRead)
async def update_invoice_part_link(
    invoice_id: int,
    link_id: int,
    data: InvoicePartLinkUpdate,
    session: AsyncSession = Depends(get_db, scope="function"),
):
    result = await session.execute(
        select(InvoicePartLink).where(
            InvoicePartLink.id == link_id,
            InvoicePartLink.invoice_id == invoice_id,
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(404, "Invoice part link not found")
    if link.is_carryover:
        raise HTTPException(400, "Привязка-перенос пересобирается автоматически и не редактируется")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(link, k, v)
    await session.flush()
    await recompute_carryover_links(session)
    await session.refresh(link)
    return link


@router.delete("/{invoice_id}/parts/{link_id}", status_code=204)
async def delete_invoice_part_link(invoice_id: int, link_id: int, session: AsyncSession = Depends(get_db, scope="function")):
    result = await session.execute(
        select(InvoicePartLink).where(
            InvoicePartLink.id == link_id,
            InvoicePartLink.invoice_id == invoice_id,
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(404, "Invoice part link not found")
    if link.is_carryover:
        raise HTTPException(400, "Привязка-перенос пересобирается автоматически и не отвязывается вручную")
    await session.delete(link)
    await session.flush()
    await recompute_carryover_links(session)
    return None
