"""
Добавляет недостающие колонки в существующей БД (после смены моделей без Alembic).
Иначе SELECT по ORM падает с «column ... does not exist» → 500 на /devices, /parts и т.д.
"""

import logging

from sqlalchemy import text

from app.database import engine

log = logging.getLogger(__name__)


# Старые колонки больше не используются моделью, но могут содержать данные.
# Их удаление при каждом старте опасно: сначала нужна отдельная миграция с бэкапом.
_LEGACY_COLUMNS_REQUIRING_MANUAL_MIGRATION = (
    ("devices", "is_active"),
    ("parts", "is_active"),
    ("parts", "uom"),
    ("orders", "status"),
    ("device_bom_items", "scrap_rate"),
    ("invoices", "currency"),
    ("invoices", "status"),
    ("invoice_part_links", "amount_allocated"),
    ("users", "session_token"),
    ("files", "storage"),
    ("files", "bucket"),
    ("files", "object_key"),
    ("files", "etag"),
)


async def _preflight_legacy_schema(conn) -> None:
    """Остановить запуск до автоматической потери старых колонок или округления BOM."""
    values = ", ".join(f"('{table}', '{column}')" for table, column in _LEGACY_COLUMNS_REQUIRING_MANUAL_MIGRATION)
    rows = (
        await conn.execute(
            text(
                "SELECT c.table_name, c.column_name FROM information_schema.columns c "
                f"JOIN (VALUES {values}) AS legacy(table_name, column_name) "
                "USING (table_name, column_name) "
                "WHERE c.table_schema = current_schema()"
            )
        )
    ).all()
    if rows:
        names = ", ".join(f"{table}.{column}" for table, column in rows)
        raise RuntimeError(
            "Обнаружены старые колонки с потенциальными данными: " + names + ". "
            "Автоматическое удаление остановлено; сначала проверьте копию БД и выполните отдельную миграцию."
        )

    qty_type = (
        await conn.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = 'device_bom_items' AND column_name = 'qty_per_device'"
            )
        )
    ).scalar_one_or_none()
    if qty_type is not None and qty_type != "integer":
        raise RuntimeError(
            "device_bom_items.qty_per_device имеет тип " + qty_type + ". "
            "Автоматическое округление значений остановлено; нужна проверенная отдельная миграция."
        )


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
        log.exception("schema_ensure: invoice_files.created_at не добавлен")
        raise RuntimeError("schema_ensure: invoice_files.created_at не добавлен") from e
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
        log.exception("schema_ensure: invoice_files ADD PRIMARY KEY не выполнен")
        raise RuntimeError("schema_ensure: invoice_files ADD PRIMARY KEY не выполнен") from e

# PostgreSQL (docker / prod)
_PG_STATEMENTS = [
    # --- devices ---
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS model VARCHAR(128)",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT false",

    # --- parts ---
    "ALTER TABLE parts ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE parts ADD COLUMN IF NOT EXISTS cipher VARCHAR(128)",
    "ALTER TABLE parts ADD COLUMN IF NOT EXISTS article VARCHAR(128)",
    "ALTER TABLE parts ADD COLUMN IF NOT EXISTS part_type VARCHAR(128)",
    "ALTER TABLE parts ADD COLUMN IF NOT EXISTS supplier VARCHAR(255)",
    "ALTER TABLE parts ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT false",

    # --- orders ---
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer VARCHAR(255)",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS contract_no VARCHAR(128)",

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
    "ALTER TABLE device_bom_items ALTER COLUMN part_id DROP NOT NULL",
    "ALTER TABLE device_bom_items ADD COLUMN IF NOT EXISTS sub_device_id INTEGER REFERENCES devices(id) ON DELETE CASCADE",
    "ALTER TABLE device_bom_items ADD COLUMN IF NOT EXISTS sub_bom_version_id INTEGER REFERENCES device_bom_versions(id) ON DELETE SET NULL",
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

    # --- invoice_part_links ---
    "ALTER TABLE invoice_part_links ADD COLUMN IF NOT EXISTS is_carryover BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE invoice_part_links ADD COLUMN IF NOT EXISTS note TEXT",
    "ALTER TABLE invoice_part_links ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",

    # --- invoice_files ---
    "ALTER TABLE invoice_files ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'original'",

    # --- users ---
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",

    # --- roles (таблицу создаёт create_all по модели) ---
    "ALTER TABLE roles ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE roles ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_roles_name_ci ON roles (lower(name))",

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
        log.exception("schema_ensure: uq_device_bom_items_bom_subdev не добавлен")
        raise RuntimeError("schema_ensure: uq_device_bom_items_bom_subdev не добавлен") from e


async def ensure_schema() -> None:
    """Привести существующую PostgreSQL-схему к текущим моделям.

    До DDL проверяем старые колонки и типы, требующие удаления или округления:
    такие преобразования проводятся только отдельной миграцией после проверки данных.

    Остальные выражения рассчитаны на повторный запуск. При первой ошибке DDL
    откатываем всю транзакцию и останавливаем приложение: PostgreSQL не позволяет
    продолжать ту же транзакцию после ошибки SQL.

    Для sqlite (тесты) ALTER-миграции не нужны: схему целиком создаёт ``create_all`` по моделям.
    """
    dialect = engine.dialect.name
    if dialect == "sqlite":
        return
    if dialect != "postgresql":
        log.warning("schema_ensure: пропуск для dialect=%s", dialect)
        return

    async with engine.connect() as conn:
        await _preflight_legacy_schema(conn)

    statements = (
        list(_PG_STATEMENTS)
        + _PG_FILES_BYTEA_MIGRATION
        + _PG_INVENTORY_SCHEMA
        + _PG_INDEXES
    )
    async with engine.begin() as conn:
        for sql in statements:
            try:
                await conn.execute(text(sql))
            except Exception as e:  # noqa: BLE001 — добавляем контекст проблемной команды
                log.error("schema_ensure: НЕ выполнено: %s — %s", sql, e)
                raise RuntimeError(f"schema_ensure: не выполнено {sql}") from e
        await _ensure_invoice_files_composite_pk_postgresql(conn)
        await _ensure_bom_subdev_unique(conn)


async def ensure_users_role_fk() -> None:
    """FK users.role → roles.code (ON DELETE RESTRICT): роль с пользователями нельзя удалить
    даже в обход API. Вызывается ПОСЛЕ ``ensure_default_roles`` (все коды ролей уже есть).

    Две фазы (NOT VALID + VALIDATE) и lock_timeout: на занятой БД не ждём блокировку
    бесконечно. Ошибка останавливает запуск: без проверенного FK защита неполна.
    """
    if engine.dialect.name != "postgresql":
        return
    try:
        async with engine.begin() as conn:
            validated = (
                await conn.execute(
                    text(
                        """
                        SELECT c.convalidated FROM pg_constraint c
                        JOIN pg_class r ON r.oid = c.conrelid
                        JOIN pg_namespace n ON n.oid = r.relnamespace
                        WHERE r.relname = 'users' AND n.nspname = current_schema()
                          AND c.conname = 'fk_users_role_roles' AND c.contype = 'f'
                        """
                    )
                )
            ).scalar_one_or_none()
            if validated is True:
                return
            await conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            if validated is None:
                await conn.execute(
                    text(
                        "ALTER TABLE users ADD CONSTRAINT fk_users_role_roles "
                        "FOREIGN KEY (role) REFERENCES roles(code) "
                        "ON UPDATE CASCADE ON DELETE RESTRICT NOT VALID"
                    )
                )
            await conn.execute(text("ALTER TABLE users VALIDATE CONSTRAINT fk_users_role_roles"))
        log.info("schema_ensure: users.role — FK fk_users_role_roles проверен")
    except Exception as e:  # noqa: BLE001
        log.exception("schema_ensure: FK users.role → roles.code не проверен; запуск остановлен")
        raise RuntimeError("FK users.role → roles.code не создан или не проверен") from e
