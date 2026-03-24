"""
Добавляет недостающие колонки в существующей БД (после смены моделей без Alembic).
Иначе SELECT по ORM падает с «column ... does not exist» → 500 на /devices, /parts и т.д.
"""

import logging

from sqlalchemy import text

from app.database import engine

log = logging.getLogger(__name__)

# PostgreSQL (docker / prod)
_PG_STATEMENTS = [
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE parts ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE device_bom_versions ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE parts DROP COLUMN IF EXISTS uom",
    "ALTER TABLE monthly_plan_parts ADD COLUMN IF NOT EXISTS qty_delivered NUMERIC(18,6) NOT NULL DEFAULT 0",
]


async def ensure_schema() -> None:
    dialect = engine.dialect.name
    if dialect not in ("postgresql", "sqlite"):
        log.warning("schema_ensure: пропуск для dialect=%s", dialect)
        return

    statements = _PG_STATEMENTS
    async with engine.begin() as conn:
        for sql in statements:
            try:
                await conn.execute(text(sql))
            except Exception as e:
                log.warning("schema_ensure: %s — %s", sql, e)
