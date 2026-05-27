"""Загрузка спецификаций (приборы + детали + BOM) одним JSON-файлом через интерфейс.

Тонкий HTTP-слой поверх логики из ``app.tools.bulk_import`` — её же использует CLI.
Файл готовит ИИ-агент по ``app/tools/IMPORT_INSTRUCTION.md``.
"""

import json

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import JSONResponse

from app.database import async_session_maker
from app.tools.bulk_import import ImportError_, import_document, parse_document

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/bom")
async def import_bom(
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="Проверить и посчитать, ничего не записывая"),
    update_existing: bool = Query(
        False, description="Пересобрать состав уже существующих версий спецификаций"
    ),
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
        except Exception as exc:  # noqa: BLE001 — откатываем и сообщаем
            await session.rollback()
            return JSONResponse(status_code=400, content={"detail": f"Ошибка загрузки: {exc}"})

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
