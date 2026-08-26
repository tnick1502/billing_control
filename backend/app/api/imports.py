"""Загрузка и выгрузка спецификаций (приборы + детали + BOM) одним JSON-файлом.

Тонкий HTTP-слой поверх логики из ``app.tools.bulk_import`` — её же использует CLI.
Файл для загрузки готовит ИИ-агент по ``app/tools/IMPORT_INSTRUCTION.md``.

Дополнительно:
- ``GET /imports/bom/export`` — выгрузить текущее состояние БД в JSON того же формата.
- ``GET /imports/db/dump`` — стримом отдать полный SQL-дамп БД (pg_dump).
"""

import asyncio
import json
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.config import settings
from app.database import async_session_maker, get_db
from app.models import Device, DeviceBomItem, DeviceBomVersion, Part, User
from app.tools.bulk_import import ImportError_, import_document, parse_document

router = APIRouter(prefix="/imports", tags=["imports"])

log = logging.getLogger(__name__)


@router.post("/bom")
async def import_bom(
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="Проверить и посчитать, ничего не записывая"),
    update_existing: bool = Query(
        False, description="Пересобрать состав уже существующих версий спецификаций"
    ),
    _: User = Depends(require_admin),
):
    raw_bytes = await file.read()
    if not raw_bytes:
        return JSONResponse(status_code=400, content={"detail": "Файл пустой"})
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return JSONResponse(status_code=400, content={"detail": f"Некорректный JSON: {exc}"})

    try:
        doc = parse_document(data)
    except ImportError_ as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    async with async_session_maker() as session:
        try:
            stats = await import_document(session, doc, update_existing=update_existing)
            if dry_run:
                await session.rollback()
            else:
                await session.commit()
        except ImportError_ as exc:
            await session.rollback()
            return JSONResponse(status_code=400, content={"detail": str(exc)})
        except Exception:  # noqa: BLE001 — откатываем; детали в лог, клиенту обобщённо
            await session.rollback()
            log.exception("imports/bom: ошибка загрузки документа")
            return JSONResponse(
                status_code=400,
                content={"detail": "Не удалось загрузить файл: проверьте формат и повторите попытку"},
            )

    return {
        "dry_run": dry_run,
        "parts_created": stats.parts_created,
        "parts_reused": stats.parts_reused,
        "devices_created": stats.devices_created,
        "devices_reused": stats.devices_reused,
        "boms_created": stats.boms_created,
        "boms_updated": stats.boms_updated,
        "boms_skipped": stats.boms_skipped,
        "items_created": stats.items_created,
        "items_skipped": stats.items_skipped,
        "warnings": stats.warnings,
    }


def _part_to_dict(p: Part) -> dict:
    out: dict = {"name": p.name}
    for key in ("cipher", "article", "part_type", "description"):
        val = getattr(p, key, None)
        if val:
            out[key] = val
    return out


@router.get("/bom/export")
async def export_bom(
    session: AsyncSession = Depends(get_db, scope="function"),
    _: User = Depends(require_admin),
):
    """Выгрузить все приборы, активные спецификации и детали в JSON формата bulk_import.

    Для каждого неархивного прибора выбирается ОДНА спецификация:
    статус ``active``/``current`` (приоритетно), иначе версия с наибольшим номером.
    Детали, не вошедшие ни в одну выгруженную спецификацию, попадают в ``parts[]``.
    """
    devices = (
        await session.execute(
            select(Device).where(Device.is_archived == False).order_by(Device.id)  # noqa: E712
        )
    ).scalars().all()

    boms = (
        await session.execute(
            select(DeviceBomVersion).order_by(
                DeviceBomVersion.device_id, DeviceBomVersion.version.desc()
            )
        )
    ).scalars().all()
    boms_by_device: dict[int, list[DeviceBomVersion]] = {}
    for b in boms:
        boms_by_device.setdefault(b.device_id, []).append(b)
    bom_by_id = {b.id: b for b in boms}

    items = (
        await session.execute(
            select(DeviceBomItem).order_by(DeviceBomItem.bom_version_id, DeviceBomItem.id)
        )
    ).scalars().all()
    items_by_bom: dict[int, list[DeviceBomItem]] = {}
    for it in items:
        items_by_bom.setdefault(it.bom_version_id, []).append(it)

    all_parts = (
        await session.execute(
            select(Part).where(Part.is_archived == False).order_by(Part.id)  # noqa: E712
        )
    ).scalars().all()
    part_by_id = {p.id: p for p in all_parts}
    dev_by_id = {d.id: d for d in devices}

    referenced_part_ids: set[int] = set()
    devices_out: list[dict] = []

    for d in devices:
        bom_list = boms_by_device.get(d.id, [])
        chosen = next((b for b in bom_list if b.status in ("active", "current")), None)
        if chosen is None and bom_list:
            chosen = max(bom_list, key=lambda b: b.version)

        dev_obj: dict = {"primary_name": d.primary_name}
        if d.model:
            dev_obj["model"] = d.model
        if d.description:
            dev_obj["description"] = d.description

        if chosen is not None:
            items_out: list[dict] = []
            for it in items_by_bom.get(chosen.id, []):
                if it.part_id is not None:
                    p = part_by_id.get(it.part_id)
                    if p is None:
                        continue
                    referenced_part_ids.add(p.id)
                    item: dict = {
                        "part": _part_to_dict(p),
                        "qty_per_device": it.qty_per_device,
                    }
                    if it.note:
                        item["note"] = it.note
                    items_out.append(item)
                elif it.sub_device_id is not None:
                    sub = dev_by_id.get(it.sub_device_id)
                    if sub is None:
                        continue
                    item = {
                        "sub_device": sub.primary_name,
                        "qty_per_device": it.qty_per_device,
                    }
                    if it.sub_bom_version_id is not None:
                        ref_bom = bom_by_id.get(it.sub_bom_version_id)
                        if ref_bom is not None:
                            item["sub_bom_version"] = ref_bom.version
                    if it.note:
                        item["note"] = it.note
                    items_out.append(item)

            bom_obj: dict = {
                "version": chosen.version,
                "status": chosen.status,
                "items": items_out,
            }
            if chosen.name:
                bom_obj["name"] = chosen.name
            if chosen.description:
                bom_obj["description"] = chosen.description
            dev_obj["bom"] = bom_obj
        devices_out.append(dev_obj)

    standalone_parts = [
        _part_to_dict(p) for p in all_parts if p.id not in referenced_part_ids
    ]

    doc = {
        "format": "billing_control.bulk_import",
        "version": 1,
        "devices": devices_out,
        "parts": standalone_parts,
    }

    body = json.dumps(doc, ensure_ascii=False, indent=2)
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"billing_control_bom_{today}.json"
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/db/dump")
async def dump_db(_: User = Depends(require_admin)):
    """Полный SQL-дамп БД через pg_dump (plain SQL, без owner/privileges)."""
    url = make_url(settings.database_url)
    host = url.host or "localhost"
    port = str(url.port or 5432)
    user = url.username or ""
    dbname = url.database or ""
    password = url.password or ""

    env = {**os.environ, "PGPASSWORD": password}
    cmd = [
        "pg_dump",
        "--format=plain",
        "--no-owner",
        "--no-privileges",
        "--encoding=UTF8",
        "-h", host,
        "-p", port,
        "-U", user,
        "-d", dbname,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError:
        return JSONResponse(
            status_code=500,
            content={"detail": "pg_dump не установлен в контейнере backend"},
        )

    async def stream():
        try:
            assert proc.stdout is not None
            while True:
                chunk = await proc.stdout.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            await proc.wait()

    today = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"billing_control_dump_{today}.sql"
    return StreamingResponse(
        stream(),
        media_type="application/sql",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
