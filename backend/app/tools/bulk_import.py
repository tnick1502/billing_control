"""Массовая загрузка приборов, деталей и спецификаций (BOM) из одного JSON-файла.

Файл готовит ИИ-агент по инструкции ``IMPORT_INSTRUCTION.md`` из «стрёмных» Excel-спек.
Формат входа описан там же и проверяется примером ``import_example.json``.

Запуск (из каталога ``backend``):

    python -m app.tools.bulk_import path/to/import.json            # залить в БД
    python -m app.tools.bulk_import path/to/import.json --dry-run   # только проверить, без записи
    python -m app.tools.bulk_import path/to/import.json --update-existing  # обновлять существующие BOM

Модуль идемпотентен: повторный прогон не создаёт дублей деталей/приборов
(совпадение по тем же правилам, что и в API). По умолчанию уже существующая
версия спецификации прибора пропускается; с ``--update-existing`` её состав
пересобирается из файла.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import Device, DeviceBomItem, DeviceBomVersion, Part

EXPECTED_FORMAT = "billing_control.bulk_import"
VALID_BOM_STATUSES = {"draft", "current", "active", "archived"}


class ImportError_(Exception):
    """Ошибка валидации входного файла (с человекочитаемым путём к проблеме)."""


# --------------------------------------------------------------------------- #
# Помощники нормализации                                                       #
# --------------------------------------------------------------------------- #
def _clean(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _part_key(name: str, article: str | None) -> tuple[str, str]:
    """Тот же ключ уникальности детали, что и в API: имя + артикул, без регистра."""
    return (name.strip().lower(), (article or "").strip().lower())


def _device_key(primary_name: str) -> str:
    return primary_name.strip().lower()


def _to_decimal(value: Any, path: str) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ImportError_(f"{path}: не число — {value!r}") from exc


def _to_int_qty(value: Any, path: str) -> int:
    try:
        qty = int(value)
    except (TypeError, ValueError) as exc:
        raise ImportError_(f"{path}: qty_per_device должен быть целым числом, получено {value!r}") from exc
    if qty < 1:
        raise ImportError_(f"{path}: qty_per_device должен быть >= 1, получено {qty}")
    return qty


# --------------------------------------------------------------------------- #
# Разбор и валидация входного файла                                            #
# --------------------------------------------------------------------------- #
@dataclass
class PartSpec:
    name: str
    cipher: str | None = None
    article: str | None = None
    description: str | None = None


@dataclass
class BomItemSpec:
    path: str
    qty_per_device: int
    part: PartSpec | None = None
    sub_device_name: str | None = None
    sub_bom_version: int | None = None
    scrap_rate: Decimal | None = None
    note: str | None = None


@dataclass
class BomSpec:
    name: str | None
    description: str | None
    version: int | None
    status: str
    items: list[BomItemSpec]


@dataclass
class DeviceSpec:
    path: str
    primary_name: str
    model: str | None = None
    description: str | None = None
    bom: BomSpec | None = None


@dataclass
class ImportDoc:
    devices: list[DeviceSpec] = field(default_factory=list)
    standalone_parts: list[PartSpec] = field(default_factory=list)


def _parse_part(raw: Any, path: str) -> PartSpec:
    if not isinstance(raw, dict):
        raise ImportError_(f"{path}: ожидался объект детали (name/cipher/article/description)")
    name = _clean(raw.get("name"))
    if not name:
        raise ImportError_(f"{path}.name: обязательное поле (наименование детали)")
    return PartSpec(
        name=name,
        cipher=_clean(raw.get("cipher")),
        article=_clean(raw.get("article")),
        description=_clean(raw.get("description")),
    )


def _parse_bom_item(raw: Any, path: str) -> BomItemSpec:
    if not isinstance(raw, dict):
        raise ImportError_(f"{path}: ожидался объект позиции спецификации")
    has_part = raw.get("part") is not None
    sub_device = _clean(raw.get("sub_device"))
    if has_part == bool(sub_device):
        raise ImportError_(
            f"{path}: укажите ровно одно из полей — 'part' (деталь) ИЛИ 'sub_device' (имя подприбора)"
        )
    qty = _to_int_qty(raw.get("qty_per_device"), f"{path}")
    item = BomItemSpec(
        path=path,
        qty_per_device=qty,
        scrap_rate=_to_decimal(raw.get("scrap_rate"), f"{path}.scrap_rate"),
        note=_clean(raw.get("note")),
    )
    if has_part:
        item.part = _parse_part(raw["part"], f"{path}.part")
    else:
        item.sub_device_name = sub_device
        sbv = raw.get("sub_bom_version")
        item.sub_bom_version = int(sbv) if sbv not in (None, "") else None
    return item


def _parse_bom(raw: Any, path: str) -> BomSpec:
    if not isinstance(raw, dict):
        raise ImportError_(f"{path}: ожидался объект спецификации (bom)")
    status = (_clean(raw.get("status")) or "active").lower()
    if status not in VALID_BOM_STATUSES:
        raise ImportError_(
            f"{path}.status: недопустимый статус {status!r}; допустимо {sorted(VALID_BOM_STATUSES)}"
        )
    items_raw = raw.get("items")
    if not isinstance(items_raw, list) or not items_raw:
        raise ImportError_(f"{path}.items: должен быть непустым списком позиций")
    version_raw = raw.get("version")
    version = int(version_raw) if version_raw not in (None, "") else None
    return BomSpec(
        name=_clean(raw.get("name")),
        description=_clean(raw.get("description")),
        version=version,
        status=status,
        items=[_parse_bom_item(it, f"{path}.items[{i}]") for i, it in enumerate(items_raw)],
    )


def _parse_device(raw: Any, path: str) -> DeviceSpec:
    if not isinstance(raw, dict):
        raise ImportError_(f"{path}: ожидался объект прибора")
    primary_name = _clean(raw.get("primary_name"))
    if not primary_name:
        raise ImportError_(f"{path}.primary_name: обязательное поле (наименование прибора)")
    dev = DeviceSpec(
        path=path,
        primary_name=primary_name,
        model=_clean(raw.get("model")),
        description=_clean(raw.get("description")),
    )
    if raw.get("bom") is not None:
        dev.bom = _parse_bom(raw["bom"], f"{path}.bom")
    return dev


def parse_document(data: Any) -> ImportDoc:
    if not isinstance(data, dict):
        raise ImportError_("Корень файла должен быть объектом JSON")
    fmt = data.get("format")
    if fmt and fmt != EXPECTED_FORMAT:
        raise ImportError_(f"format: ожидался {EXPECTED_FORMAT!r}, получено {fmt!r}")

    doc = ImportDoc()
    devices_raw = data.get("devices") or []
    if not isinstance(devices_raw, list):
        raise ImportError_("devices: должен быть списком")
    doc.devices = [_parse_device(d, f"devices[{i}]") for i, d in enumerate(devices_raw)]

    parts_raw = data.get("parts") or []
    if not isinstance(parts_raw, list):
        raise ImportError_("parts: должен быть списком")
    doc.standalone_parts = [_parse_part(p, f"parts[{i}]") for i, p in enumerate(parts_raw)]

    if not doc.devices and not doc.standalone_parts:
        raise ImportError_("Файл пуст: нет ни devices, ни parts")

    # Запрещаем цикл «прибор сам себе подприбор»; недостающие подприборы мягко
    # проверим в фазе записи (там виден и состав БД).
    for dev in doc.devices:
        if not dev.bom:
            continue
        for item in dev.bom.items:
            if item.sub_device_name and _device_key(item.sub_device_name) == _device_key(dev.primary_name):
                raise ImportError_(f"{item.path}: прибор не может быть собственным подприбором (цикл)")
    return doc


# --------------------------------------------------------------------------- #
# Запись в БД                                                                  #
# --------------------------------------------------------------------------- #
@dataclass
class Stats:
    parts_created: int = 0
    parts_reused: int = 0
    devices_created: int = 0
    devices_reused: int = 0
    boms_created: int = 0
    boms_skipped: int = 0
    boms_updated: int = 0
    items_created: int = 0
    items_skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            "Итоги загрузки:",
            f"  Детали:        создано {self.parts_created}, переиспользовано {self.parts_reused}",
            f"  Приборы:       создано {self.devices_created}, переиспользовано {self.devices_reused}",
            f"  Спецификации:  создано {self.boms_created}, обновлено {self.boms_updated}, пропущено {self.boms_skipped}",
            f"  Позиции BOM:   создано {self.items_created}, пропущено (дубли) {self.items_skipped}",
        ]
        if self.warnings:
            lines.append(f"  Предупреждения ({len(self.warnings)}):")
            lines += [f"    - {w}" for w in self.warnings]
        return "\n".join(lines)


async def _get_or_create_part(
    session: AsyncSession, spec: PartSpec, cache: dict[tuple[str, str], Part], stats: Stats
) -> Part:
    key = _part_key(spec.name, spec.article)
    if key in cache:
        return cache[key]

    existing = await session.scalar(
        select(Part).where(
            func.lower(Part.name) == key[0],
            func.coalesce(func.lower(Part.article), "") == key[1],
        ).limit(1)
    )
    if existing:
        cache[key] = existing
        stats.parts_reused += 1
        return existing

    part = Part(name=spec.name, cipher=spec.cipher, article=spec.article, description=spec.description)
    session.add(part)
    await session.flush()
    cache[key] = part
    stats.parts_created += 1
    return part


async def _get_or_create_device(
    session: AsyncSession, spec: DeviceSpec, cache: dict[str, Device], stats: Stats
) -> Device:
    key = _device_key(spec.primary_name)
    if key in cache:
        return cache[key]

    existing = await session.scalar(
        select(Device).where(func.lower(Device.primary_name) == key).limit(1)
    )
    if existing:
        cache[key] = existing
        stats.devices_reused += 1
        return existing

    device = Device(primary_name=spec.primary_name, model=spec.model, description=spec.description)
    session.add(device)
    await session.flush()
    cache[key] = device
    stats.devices_created += 1
    return device


async def _next_bom_version(session: AsyncSession, device_id: int) -> int:
    current_max = await session.scalar(
        select(func.max(DeviceBomVersion.version)).where(DeviceBomVersion.device_id == device_id)
    )
    return (current_max or 0) + 1


async def import_document(
    session: AsyncSession, doc: ImportDoc, *, update_existing: bool
) -> Stats:
    stats = Stats()
    part_cache: dict[tuple[str, str], Part] = {}
    device_cache: dict[str, Device] = {}

    # Фаза 1: standalone-детали (часто их нет, но поддерживаем).
    for spec in doc.standalone_parts:
        await _get_or_create_part(session, spec, part_cache, stats)

    # Фаза 2: создаём/находим все приборы, чтобы ссылки на подприборы разрешались.
    for dev_spec in doc.devices:
        await _get_or_create_device(session, dev_spec, device_cache, stats)

    # Фаза 3: спецификации и их позиции.
    for dev_spec in doc.devices:
        if not dev_spec.bom:
            continue
        device = device_cache[_device_key(dev_spec.primary_name)]
        bom_spec = dev_spec.bom

        # Подбираем версию: либо явная из файла, либо следующая свободная.
        version = bom_spec.version if bom_spec.version is not None else await _next_bom_version(session, device.id)

        existing_bom = await session.scalar(
            select(DeviceBomVersion).where(
                DeviceBomVersion.device_id == device.id,
                DeviceBomVersion.version == version,
            )
        )

        if existing_bom and not update_existing:
            stats.boms_skipped += 1
            stats.warnings.append(
                f"{dev_spec.path}: спецификация v{version} для «{device.primary_name}» уже есть — пропущена "
                f"(используйте --update-existing для пересборки)"
            )
            continue

        if existing_bom and update_existing:
            await session.execute(
                delete(DeviceBomItem).where(DeviceBomItem.bom_version_id == existing_bom.id)
            )
            existing_bom.name = bom_spec.name or existing_bom.name
            existing_bom.description = bom_spec.description
            existing_bom.status = bom_spec.status
            bom = existing_bom
            stats.boms_updated += 1
        else:
            bom = DeviceBomVersion(
                device_id=device.id,
                name=bom_spec.name or f"Спецификация v{version}",
                description=bom_spec.description,
                version=version,
                status=bom_spec.status,
            )
            session.add(bom)
            await session.flush()
            stats.boms_created += 1

        # Статус active/current — единственный на прибор: остальные архивируем (как в API).
        if bom_spec.status in ("active", "current"):
            await session.execute(
                update(DeviceBomVersion)
                .where(
                    DeviceBomVersion.device_id == device.id,
                    DeviceBomVersion.id != bom.id,
                    DeviceBomVersion.status == bom_spec.status,
                )
                .values(status="archived")
            )

        # Позиции спецификации.
        seen_parts: set[int] = set()
        seen_subdevs: set[int] = set()
        for item in bom_spec.items:
            if item.part is not None:
                part = await _get_or_create_part(session, item.part, part_cache, stats)
                if part.id in seen_parts:
                    stats.items_skipped += 1
                    stats.warnings.append(f"{item.path}: деталь «{part.name}» уже в этой спецификации — пропущена")
                    continue
                seen_parts.add(part.id)
                session.add(DeviceBomItem(
                    bom_version_id=bom.id,
                    part_id=part.id,
                    qty_per_device=item.qty_per_device,
                    scrap_rate=item.scrap_rate,
                    note=item.note,
                ))
                stats.items_created += 1
            else:
                sub_key = _device_key(item.sub_device_name)  # type: ignore[arg-type]
                sub_device = device_cache.get(sub_key)
                if sub_device is None:
                    sub_device = await session.scalar(
                        select(Device).where(func.lower(Device.primary_name) == sub_key).limit(1)
                    )
                    if sub_device:
                        device_cache[sub_key] = sub_device
                if sub_device is None:
                    stats.items_skipped += 1
                    stats.warnings.append(
                        f"{item.path}: подприбор «{item.sub_device_name}» не найден ни в файле, ни в БД — позиция пропущена"
                    )
                    continue
                if sub_device.id in seen_subdevs:
                    stats.items_skipped += 1
                    stats.warnings.append(f"{item.path}: подприбор «{sub_device.primary_name}» уже в этой спецификации — пропущен")
                    continue
                seen_subdevs.add(sub_device.id)

                sub_bom_version_id: int | None = None
                if item.sub_bom_version is not None:
                    sub_bom = await session.scalar(
                        select(DeviceBomVersion).where(
                            DeviceBomVersion.device_id == sub_device.id,
                            DeviceBomVersion.version == item.sub_bom_version,
                        )
                    )
                    if sub_bom:
                        sub_bom_version_id = sub_bom.id
                    else:
                        stats.warnings.append(
                            f"{item.path}: у подприбора «{sub_device.primary_name}» нет спецификации "
                            f"v{item.sub_bom_version} — ссылка оставлена пустой"
                        )

                session.add(DeviceBomItem(
                    bom_version_id=bom.id,
                    sub_device_id=sub_device.id,
                    sub_bom_version_id=sub_bom_version_id,
                    qty_per_device=item.qty_per_device,
                    note=item.note,
                ))
                stats.items_created += 1

    await session.flush()
    return stats


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
async def _run(path: Path, *, dry_run: bool, update_existing: bool) -> int:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"Файл не найден: {path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"Некорректный JSON: {exc}", file=sys.stderr)
        return 2

    try:
        doc = parse_document(raw)
    except ImportError_ as exc:
        print(f"Ошибка валидации: {exc}", file=sys.stderr)
        return 2

    async with async_session_maker() as session:
        try:
            stats = await import_document(session, doc, update_existing=update_existing)
            if dry_run:
                await session.rollback()
                print("[DRY-RUN] изменения откатаны, в БД ничего не записано.\n")
            else:
                await session.commit()
        except ImportError_ as exc:
            await session.rollback()
            print(f"Ошибка валидации: {exc}", file=sys.stderr)
            return 2
        except Exception as exc:  # noqa: BLE001 — печатаем и откатываем
            await session.rollback()
            print(f"Ошибка при записи в БД (всё откатано): {exc}", file=sys.stderr)
            return 1

    print(stats.render())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Массовая загрузка приборов, деталей и спецификаций из JSON-файла.",
    )
    parser.add_argument("file", type=Path, help="путь к подготовленному JSON-файлу (см. IMPORT_INSTRUCTION.md)")
    parser.add_argument("--dry-run", action="store_true", help="проверить и посчитать, но НЕ записывать в БД")
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="пересобрать состав уже существующих версий спецификаций (по умолчанию они пропускаются)",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.file, dry_run=args.dry_run, update_existing=args.update_existing))


if __name__ == "__main__":
    raise SystemExit(main())
