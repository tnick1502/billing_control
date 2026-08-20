"""
Добавляет недостающие колонки в существующей БД (после смены моделей без Alembic).
Иначе SELECT по ORM падает с «column ... does not exist» → 500 на /devices, /parts и т.д.
"""

import logging

from sqlalchemy import text

from app.database import engine

log = logging.getLogger(__name__)


def _safe_pg_ident(name: str) -> bool:
    return bool(name) and name.replace("_", "").isalnum()


async def _ensure_invoice_files_composite_pk_postgresql(conn) -> None:
    """
    Несколько файлов на один счёт: PRIMARY KEY (invoice_id, file_id).

    Старые БД: PK или UNIQUE только по invoice_id → вторая вставка (upload) даёт 500.
    """
    try:
        await conn.execute(
            text(
                """
                ALTER TABLE invoice_files
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                """
            )
        )
    except Exception as e:
        log.warning("schema_ensure: invoice_files.created_at — %s", e)
    result = await conn.execute(
        text(
            """
            SELECT c.conname,
                   c.contype::text AS ctype,
                   (
                       SELECT array_agg(a.attname ORDER BY u.ord)
                       FROM unnest(c.conkey) WITH ORDINALITY AS u(attnum, ord)
                       JOIN pg_attribute a
                         ON a.attrelid = c.conrelid AND a.attnum = u.attnum AND a.attnum > 0
                   ) AS cols
            FROM pg_constraint c
            JOIN pg_class r ON r.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = r.relnamespace
            WHERE r.relname = 'invoice_files'
              AND n.nspname = current_schema()
              AND c.contype IN ('p', 'u')
            """
        )
    )
    rows = result.all()
    goal = frozenset({"invoice_id", "file_id"})

    def cols_set(cols) -> frozenset:
        return frozenset(cols) if cols else frozenset()

    if any(r[1] == "p" and cols_set(r[2]) == goal for r in rows):
        return

    for conname, ctype, cols in rows:
        if cols is None:
            continue
        name = str(conname)
        if not _safe_pg_ident(name):
            log.warning("schema_ensure: invoice_files: пропуск ограничения с необычным именем %r", name)
            continue
        cs = cols_set(cols)
        if ctype == "p" and cs == goal:
            continue
        if cs == frozenset({"invoice_id"}):
            await conn.execute(text(f'ALTER TABLE invoice_files DROP CONSTRAINT "{name}"'))
            log.info(
                "schema_ensure: invoice_files — удалено ограничение %s (%s) %s",
                name,
                ctype,
                list(cols),
            )
        elif ctype == "p" and cs != goal:
            await conn.execute(text(f'ALTER TABLE invoice_files DROP CONSTRAINT "{name}"'))
            log.info("schema_ensure: invoice_files — снят PK %s %s", name, list(cols))

    result2 = await conn.execute(
        text(
            """
            SELECT c.conname,
                   c.contype::text AS ctype,
                   (
                       SELECT array_agg(a.attname ORDER BY u.ord)
                       FROM unnest(c.conkey) WITH ORDINALITY AS u(attnum, ord)
                       JOIN pg_attribute a
                         ON a.attrelid = c.conrelid AND a.attnum = u.attnum AND a.attnum > 0
                   ) AS cols
            FROM pg_constraint c
            JOIN pg_class r ON r.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = r.relnamespace
            WHERE r.relname = 'invoice_files'
              AND n.nspname = current_schema()
              AND c.contype IN ('p', 'u')
            """
        )
    )
    rows_after = result2.all()
    if any(r[1] == "p" and cols_set(r[2]) == goal for r in rows_after):
        return
    try:
        await conn.execute(text("ALTER TABLE invoice_files ADD PRIMARY KEY (invoice_id, file_id)"))
        log.info("schema_ensure: invoice_files — добавлен PRIMARY KEY (invoice_id, file_id)")
    except Exception as e:
        log.warning("schema_ensure: invoice_files ADD PRIMARY KEY — %s", e)

# PostgreSQL (docker / prod)
_PG_STATEMENTS = [
    # --- devices ---
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS model VARCHAR(128)",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE devices DROP COLUMN IF EXISTS is_active",

    # --- parts ---
    "ALTER TABLE parts ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE parts ADD COLUMN IF NOT EXISTS cipher VARCHAR(128)",
    "ALTER TABLE parts ADD COLUMN IF NOT EXISTS article VARCHAR(128)",
    "ALTER TABLE parts ADD COLUMN IF NOT EXISTS part_type VARCHAR(128)",
    "ALTER TABLE parts ADD COLUMN IF NOT EXISTS supplier VARCHAR(255)",
    "ALTER TABLE parts ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE parts DROP COLUMN IF EXISTS is_active",
    "ALTER TABLE parts DROP COLUMN IF EXISTS uom",

    # --- orders ---
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer VARCHAR(255)",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS contract_no VARCHAR(128)",
    "ALTER TABLE orders DROP COLUMN IF EXISTS status",

    # --- order_items ---
    "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS price NUMERIC(18,2)",
    "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS note TEXT",

    # --- order_part_items ---
    "ALTER TABLE order_part_items ADD COLUMN IF NOT EXISTS price NUMERIC(18,2)",
    "ALTER TABLE order_part_items ADD COLUMN IF NOT EXISTS note TEXT",

    # --- device_bom_versions ---
    "ALTER TABLE device_bom_versions ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE device_bom_versions ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ NOT NULL DEFAULT now()",
    "ALTER TABLE device_bom_versions ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ",

    # --- device_bom_items ---
    "ALTER TABLE device_bom_items ALTER COLUMN qty_per_device TYPE INTEGER USING ROUND(qty_per_device)::integer",
    "ALTER TABLE device_bom_items ALTER COLUMN part_id DROP NOT NULL",
    "ALTER TABLE device_bom_items ADD COLUMN IF NOT EXISTS sub_device_id INTEGER REFERENCES devices(id) ON DELETE CASCADE",
    "ALTER TABLE device_bom_items ADD COLUMN IF NOT EXISTS sub_bom_version_id INTEGER REFERENCES device_bom_versions(id) ON DELETE SET NULL",
    # scrap_rate удалён из модели — выкидываем колонку, если осталась от старой схемы.
    "ALTER TABLE device_bom_items DROP COLUMN IF EXISTS scrap_rate",
    "ALTER TABLE device_bom_items ADD COLUMN IF NOT EXISTS note TEXT",

    # --- monthly_plans ---
    "ALTER TABLE monthly_plans ADD COLUMN IF NOT EXISTS generated_by VARCHAR(128)",
    "ALTER TABLE monthly_plans ADD COLUMN IF NOT EXISTS note TEXT",

    # --- monthly_plan_parts ---
    "ALTER TABLE monthly_plan_parts ADD COLUMN IF NOT EXISTS qty_delivered NUMERIC(18,6) NOT NULL DEFAULT 0",
    # qty_final: NOT NULL — DEFAULT 0 для обратной совместимости; пересчитывается при generate_monthly_plan
    "ALTER TABLE monthly_plan_parts ADD COLUMN IF NOT EXISTS qty_final NUMERIC(18,6) NOT NULL DEFAULT 0",

    # --- invoices ---
    "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS supplier VARCHAR(255)",
    "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS note TEXT",
    "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS payment_date DATE",
    "ALTER TABLE invoices DROP COLUMN IF EXISTS currency",
    "ALTER TABLE invoices DROP COLUMN IF EXISTS status",

    # --- invoice_part_links ---
    "ALTER TABLE invoice_part_links DROP COLUMN IF EXISTS amount_allocated",
    "ALTER TABLE invoice_part_links ADD COLUMN IF NOT EXISTS is_carryover BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE invoice_part_links ADD COLUMN IF NOT EXISTS note TEXT",
    "ALTER TABLE invoice_part_links ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",

    # --- invoice_files ---
    "ALTER TABLE invoice_files ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'original'",

    # --- users ---
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255)",
    # session_token больше не используется — сессии вынесены в таблицу user_sessions (только хэш токена).
    "ALTER TABLE users DROP COLUMN IF EXISTS session_token",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",

    # --- audit_logs ---
    "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS username VARCHAR(64)",
    "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS role VARCHAR(32)",
    "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS method VARCHAR(16)",
    "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS path VARCHAR(512)",
    "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS status_code INTEGER",
    "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS details TEXT",
]

# Инвентаризация хранится отдельно от счетов. Последняя таблица — производный кэш
# распределения физически найденных остатков по строкам планов; он пересобирается
# атомарно вместе с обычными переносами.
_PG_INVENTORY_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS inventory_documents (
        id SERIAL PRIMARY KEY,
        month DATE NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'posted',
        note TEXT,
        created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        updated_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_inventory_documents_month UNIQUE (month),
        CONSTRAINT ck_inventory_documents_status CHECK (status IN ('posted', 'cancelled')),
        CONSTRAINT ck_inventory_documents_month_start
            CHECK (month = date_trunc('month', month)::date)
    )""",
    """CREATE TABLE IF NOT EXISTS inventory_items (
        id SERIAL PRIMARY KEY,
        inventory_id INTEGER NOT NULL REFERENCES inventory_documents(id) ON DELETE CASCADE,
        part_id INTEGER NOT NULL REFERENCES parts(id) ON DELETE RESTRICT,
        qty_found NUMERIC(18,6) NOT NULL,
        note TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_inventory_items_inventory_part UNIQUE (inventory_id, part_id),
        CONSTRAINT ck_inventory_items_qty_found_positive CHECK (qty_found > 0)
    )""",
    """CREATE TABLE IF NOT EXISTS inventory_plan_allocations (
        id SERIAL PRIMARY KEY,
        inventory_item_id INTEGER NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
        plan_id INTEGER NOT NULL REFERENCES monthly_plans(id) ON DELETE CASCADE,
        part_id INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
        qty_covered NUMERIC(18,6) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_inventory_plan_allocations_source_plan_part
            UNIQUE (inventory_item_id, plan_id, part_id),
        CONSTRAINT ck_inventory_plan_allocations_qty_positive CHECK (qty_covered > 0)
    )""",
]

# Индексы по внешним ключам/частым фильтрам. PostgreSQL НЕ индексирует FK автоматически —
# без этого на удалённой БД растущие таблицы дают seq-scan (медленные планы/счета/статистика).
# Все CREATE INDEX IF NOT EXISTS идемпотентны.
_PG_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_order_items_order_id ON order_items (order_id)",
    "CREATE INDEX IF NOT EXISTS ix_order_items_bom_version_id ON order_items (bom_version_id)",
    "CREATE INDEX IF NOT EXISTS ix_order_items_device_id ON order_items (device_id)",
    "CREATE INDEX IF NOT EXISTS ix_order_part_items_order_id ON order_part_items (order_id)",
    "CREATE INDEX IF NOT EXISTS ix_order_part_items_part_id ON order_part_items (part_id)",
    "CREATE INDEX IF NOT EXISTS ix_orders_order_date ON orders (order_date)",
    "CREATE INDEX IF NOT EXISTS ix_invoice_part_links_plan_id ON invoice_part_links (plan_id)",
    "CREATE INDEX IF NOT EXISTS ix_invoice_part_links_part_id ON invoice_part_links (part_id)",
    "CREATE INDEX IF NOT EXISTS ix_invoice_part_links_invoice_id ON invoice_part_links (invoice_id)",
    "CREATE INDEX IF NOT EXISTS ix_monthly_plan_devices_bom_version_id ON monthly_plan_devices (bom_version_id)",
    "CREATE INDEX IF NOT EXISTS ix_device_bom_items_sub_bom_version_id ON device_bom_items (sub_bom_version_id)",
    "CREATE INDEX IF NOT EXISTS ix_user_sessions_expires_at ON user_sessions (expires_at)",
    # Поиск по file_id (составной PK ведёт по другому столбцу): удаление файлов-сирот и проверка доступа к скачиванию.
    "CREATE INDEX IF NOT EXISTS ix_invoice_files_file_id ON invoice_files (file_id)",
    "CREATE INDEX IF NOT EXISTS ix_monthly_plan_part_files_file_id ON monthly_plan_part_files (file_id)",
    "CREATE INDEX IF NOT EXISTS ix_inventory_items_part_id ON inventory_items (part_id)",
    "CREATE INDEX IF NOT EXISTS ix_inventory_plan_allocations_plan_part ON inventory_plan_allocations (plan_id, part_id)",
    "CREATE INDEX IF NOT EXISTS ix_inventory_plan_allocations_inventory_item_id ON inventory_plan_allocations (inventory_item_id)",
]

# Вложения: таблица байтов и приведение старых колонок files к текущей модели (если были)
_PG_FILES_BYTEA_MIGRATION = [
    """CREATE TABLE IF NOT EXISTS file_contents (
        file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
        data BYTEA NOT NULL,
        PRIMARY KEY (file_id)
    )""",
    "ALTER TABLE files ADD COLUMN IF NOT EXISTS filename VARCHAR(512)",
    "UPDATE files SET filename = 'legacy.bin' WHERE filename IS NULL",
    "ALTER TABLE files ALTER COLUMN filename SET NOT NULL",
    "ALTER TABLE files ADD COLUMN IF NOT EXISTS content_type VARCHAR(128)",
    "ALTER TABLE files ADD COLUMN IF NOT EXISTS size_bytes BIGINT",
    "ALTER TABLE files ADD COLUMN IF NOT EXISTS uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    "ALTER TABLE files DROP CONSTRAINT IF EXISTS uq_files_bucket_key",
    "ALTER TABLE files DROP COLUMN IF EXISTS storage",
    "ALTER TABLE files DROP COLUMN IF EXISTS bucket",
    "ALTER TABLE files DROP COLUMN IF EXISTS object_key",
    "ALTER TABLE files DROP COLUMN IF EXISTS etag",
]


async def _ensure_bom_subdev_unique(conn) -> None:
    """Add UNIQUE(bom_version_id, sub_device_id) to device_bom_items if missing."""
    result = await conn.execute(
        text(
            """
            SELECT 1 FROM pg_constraint c
            JOIN pg_class r ON r.oid = c.conrelid
            WHERE r.relname = 'device_bom_items'
              AND c.conname = 'uq_device_bom_items_bom_subdev'
            """
        )
    )
    if result.fetchone():
        return
    try:
        await conn.execute(
            text(
                "ALTER TABLE device_bom_items "
                "ADD CONSTRAINT uq_device_bom_items_bom_subdev "
                "UNIQUE (bom_version_id, sub_device_id)"
            )
        )
        log.info("schema_ensure: device_bom_items — added UNIQUE(bom_version_id, sub_device_id)")
    except Exception as e:
        log.warning("schema_ensure: uq_device_bom_items_bom_subdev — %s", e)


async def ensure_schema() -> None:
    """Привести существующую PostgreSQL-схему к текущим моделям.

    Все выражения идемпотентны (IF EXISTS / IF NOT EXISTS / приведение к тому же типу),
    поэтому в норме не падают. Если хоть одно упало — это реальная проблема схемы:
    собираем ВСЕ ошибки, логируем и поднимаем исключение, чтобы приложение НЕ стартовало
    с полу-мигрированной БД (раньше ошибки молча проглатывались — отсюда тихая порча данных).

    Для sqlite (тесты) ALTER-миграции не нужны: схему целиком создаёт ``create_all`` по моделям.
    """
    dialect = engine.dialect.name
    if dialect == "sqlite":
        return
    if dialect != "postgresql":
        log.warning("schema_ensure: пропуск для dialect=%s", dialect)
        return

    statements = (
        list(_PG_STATEMENTS)
        + _PG_FILES_BYTEA_MIGRATION
        + _PG_INVENTORY_SCHEMA
        + _PG_INDEXES
    )
    failures: list[str] = []
    async with engine.begin() as conn:
        for sql in statements:
            try:
                await conn.execute(text(sql))
            except Exception as e:  # noqa: BLE001 — копим все ошибки, чтобы показать разом
                log.error("schema_ensure: НЕ выполнено: %s — %s", sql, e)
                failures.append(f"{sql} -> {e}")
        await _ensure_invoice_files_composite_pk_postgresql(conn)
        await _ensure_bom_subdev_unique(conn)

    if failures:
        raise RuntimeError(
            "schema_ensure: не удалось привести схему БД к моделям; приложение остановлено. "
            f"Проблемные операции ({len(failures)}): " + " | ".join(failures)
        )
