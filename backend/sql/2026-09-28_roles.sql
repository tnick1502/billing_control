-- Роли и права доступа (редактор ролей в админке).
-- Скрипт идемпотентен и НЕОБЯЗАТЕЛЕН: то же самое backend делает сам при старте
-- (create_all + schema_ensure + ensure_default_roles + ensure_users_role_fk).
-- Нужен, если хотите применить изменения схемы вручную и заранее, до выкатки backend.
--
-- Изменения только добавляющие: новая таблица roles и FK users.role → roles.code.
-- Старая версия backend с этой схемой продолжает работать (откат = деплой прошлого коммита).

BEGIN;

-- На загруженном проде не ждём блокировки бесконечно: при тайм-ауте вся
-- транзакция откатится, после чего скрипт можно безопасно повторить.
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

CREATE TABLE IF NOT EXISTS roles (
    id           SERIAL PRIMARY KEY,
    code         VARCHAR(32)  NOT NULL UNIQUE,
    name         VARCHAR(128) NOT NULL,
    description  TEXT,
    is_system    BOOLEAN NOT NULL DEFAULT false,
    is_superuser BOOLEAN NOT NULL DEFAULT false,
    permissions  JSONB   NOT NULL DEFAULT '{}'::jsonb,
    revision     INTEGER NOT NULL DEFAULT 1,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_roles_name_ci ON roles (lower(name));

-- Системные роли. Пресет «Сотрудник» = ровно прежние права сотрудника.
INSERT INTO roles (code, name, description, is_system, is_superuser, permissions) VALUES
  ('admin', 'Администратор', 'Системная роль: полный доступ, управление пользователями и ролями',
   true, true, '{}'::jsonb),
  ('employee', 'Сотрудник', 'Планы — полностью, счета — без удаления, остальное — просмотр',
   false, false,
   '{"monthly_plans":"full","invoices":"edit","parts":"view","devices":"view",
     "bom":"view","orders":"view","statistics":"view","import":"none"}'::jsonb)
ON CONFLICT (code) DO NOTHING;

-- Страховка: если у пользователей встречается неизвестный код роли — роль без прав.
INSERT INTO roles (code, name, permissions)
SELECT DISTINCT u.role, 'Роль ' || u.role, '{}'::jsonb
FROM users u
WHERE NOT EXISTS (SELECT 1 FROM roles r WHERE r.code = u.role)
ON CONFLICT (code) DO NOTHING;

-- Роль с пользователями нельзя удалить даже в обход API.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
    JOIN pg_class r ON r.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = r.relnamespace
    WHERE r.relname = 'users' AND n.nspname = current_schema() AND c.conname = 'fk_users_role_roles'
  ) THEN
    ALTER TABLE users ADD CONSTRAINT fk_users_role_roles
      FOREIGN KEY (role) REFERENCES roles(code) ON UPDATE CASCADE ON DELETE RESTRICT NOT VALID;
    ALTER TABLE users VALIDATE CONSTRAINT fk_users_role_roles;
  END IF;
END $$;

COMMIT;
