import re
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Invoice, File as FileModel, InvoiceFile, InvoicePartLink
from app.schemas.common import (
    InvoiceCreate,
    InvoiceRead,
    InvoiceUpdate,
    InvoicePartLinkCreate,
    InvoicePartLinkRead,
    InvoicePartLinkUpdate,
    FileRead,
)
from app.services.s3_service import upload_file, ensure_bucket_exists, get_presigned_url

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("", response_model=list[InvoiceRead])
async def list_invoices(session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Invoice).order_by(Invoice.invoice_date.desc()))
    return result.scalars().all()


async def _generate_invoice_no(session: AsyncSession) -> str:
    """Generate next invoice number: INV-001, INV-002, ..."""
    result = await session.execute(select(Invoice.invoice_no))
    max_num = 0
    for row in result.scalars().all():
        m = re.match(r"INV-(\d+)", row.invoice_no or "", re.IGNORECASE)
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"INV-{max_num + 1:03d}"


@router.post("", response_model=InvoiceRead)
async def create_invoice(data: InvoiceCreate, session: AsyncSession = Depends(get_db)):
    dump = data.model_dump()
    if not dump.get("invoice_no") or not str(dump.get("invoice_no") or "").strip():
        dump["invoice_no"] = await _generate_invoice_no(session)
    invoice = Invoice(**dump)
    session.add(invoice)
    await session.flush()
    await session.refresh(invoice)
    return invoice


@router.get("/{invoice_id}", response_model=InvoiceRead)
async def get_invoice(invoice_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    return invoice


@router.patch("/{invoice_id}", response_model=InvoiceRead)
async def update_invoice(invoice_id: int, data: InvoiceUpdate, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    update_data = data.model_dump(exclude_unset=True)
    update_data.pop("invoice_no", None)  # invoice_no immutable
    for k, v in update_data.items():
        setattr(invoice, k, v)
    await session.flush()
    await session.refresh(invoice)
    return invoice


@router.delete("/{invoice_id}", status_code=204)
async def delete_invoice(invoice_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    await session.delete(invoice)
    return None


@router.get("/{invoice_id}/files", response_model=list[FileRead])
async def list_invoice_files(invoice_id: int, session: AsyncSession = Depends(get_db)):
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
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "Invoice not found")

    await ensure_bucket_exists()
    object_key, etag, size = await upload_file(
        file.file,
        file.filename or "document",
        file.content_type,
    )

    db_file = FileModel(
        storage="s3",
        bucket=settings.s3_bucket,
        object_key=object_key,
        etag=etag,
        content_type=file.content_type,
        size_bytes=size,
    )
    session.add(db_file)
    await session.flush()

    inv_file = InvoiceFile(invoice_id=invoice_id, file_id=db_file.id, role="original")
    session.add(inv_file)
    await session.flush()
    await session.refresh(db_file)
    return db_file


@router.get("/{invoice_id}/parts", response_model=list[InvoicePartLinkRead])
async def list_invoice_parts(invoice_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(InvoicePartLink).where(InvoicePartLink.invoice_id == invoice_id))
    return result.scalars().all()


@router.post("/{invoice_id}/parts", response_model=InvoicePartLinkRead)
async def create_invoice_part_link(
    invoice_id: int,
    data: InvoicePartLinkCreate,
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(select(Invoice).where(Invoice.id == invoice_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Invoice not found")
    link = InvoicePartLink(invoice_id=invoice_id, **data.model_dump())
    session.add(link)
    await session.flush()
    await session.refresh(link)
    return link


@router.patch("/{invoice_id}/parts/{link_id}", response_model=InvoicePartLinkRead)
async def update_invoice_part_link(
    invoice_id: int,
    link_id: int,
    data: InvoicePartLinkUpdate,
    session: AsyncSession = Depends(get_db),
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
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(link, k, v)
    await session.flush()
    await session.refresh(link)
    return link


@router.delete("/{invoice_id}/parts/{link_id}", status_code=204)
async def delete_invoice_part_link(invoice_id: int, link_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(InvoicePartLink).where(
            InvoicePartLink.id == link_id,
            InvoicePartLink.invoice_id == invoice_id,
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(404, "Invoice part link not found")
    await session.delete(link)
    return None


@router.get("/files/{file_id}/presigned-url")
async def get_file_presigned_url(file_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(FileModel).where(FileModel.id == file_id))
    f = result.scalar_one_or_none()
    if not f:
        raise HTTPException(404, "File not found")
    url = get_presigned_url(f.bucket, f.object_key)
    return {"url": url}
