-- Инвентаризация и её распределение по месячным планам.
-- Скрипт идемпотентен: его можно безопасно выполнить повторно в PostgreSQL.
-- Применять ДО запуска версии backend, которая использует эти таблицы.

BEGIN;

-- На загруженном проде не ждём блокировки бесконечно: при тайм-ауте вся
-- транзакция откатится, после чего скрипт можно безопасно повторить.
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

CREATE TABLE IF NOT EXISTS inventory_documents (
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
);

CREATE TABLE IF NOT EXISTS inventory_items (
    id SERIAL PRIMARY KEY,
    inventory_id INTEGER NOT NULL REFERENCES inventory_documents(id) ON DELETE CASCADE,
    part_id INTEGER NOT NULL REFERENCES parts(id) ON DELETE RESTRICT,
    qty_found NUMERIC(18,6) NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_inventory_items_inventory_part UNIQUE (inventory_id, part_id),
    CONSTRAINT ck_inventory_items_qty_found_positive CHECK (qty_found > 0)
);

CREATE TABLE IF NOT EXISTS inventory_plan_allocations (
    id SERIAL PRIMARY KEY,
    inventory_item_id INTEGER NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
    plan_id INTEGER NOT NULL REFERENCES monthly_plans(id) ON DELETE CASCADE,
    part_id INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    qty_covered NUMERIC(18,6) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_inventory_plan_allocations_source_plan_part
        UNIQUE (inventory_item_id, plan_id, part_id),
    CONSTRAINT ck_inventory_plan_allocations_qty_positive CHECK (qty_covered > 0)
);

CREATE INDEX IF NOT EXISTS ix_inventory_items_part_id
    ON inventory_items (part_id);
CREATE INDEX IF NOT EXISTS ix_inventory_plan_allocations_plan_part
    ON inventory_plan_allocations (plan_id, part_id);
CREATE INDEX IF NOT EXISTS ix_inventory_plan_allocations_inventory_item_id
    ON inventory_plan_allocations (inventory_item_id);

COMMIT;
