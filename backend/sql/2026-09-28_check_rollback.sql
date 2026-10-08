-- Запустить ДО отката backend на код без редактора ролей:
-- psql -X --set=ON_ERROR_STOP=on --dbname="$DATABASE_URL_PSQL" \
--   --file=backend/sql/2026-09-28_check_rollback.sql
-- Скрипт ничего не меняет. Код прошлого коммита считает любую нестандартную
-- активную роль сотрудником и использует прежние, жёстко заданные права employee.

BEGIN TRANSACTION READ ONLY;

SELECT username, role
FROM users
WHERE is_active AND role NOT IN ('admin', 'employee')
ORDER BY username;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM users
    WHERE is_active AND role NOT IN ('admin', 'employee')
  ) THEN
    RAISE EXCEPTION 'Откат запрещён: активные пользователи нестандартных ролей получат права сотрудника. Сначала отключите их или осознанно переназначьте.';
  END IF;

  IF EXISTS (SELECT 1 FROM users WHERE is_active AND role = 'employee')
     AND NOT EXISTS (
       SELECT 1 FROM roles
       WHERE code = 'employee'
         AND is_superuser = false
         AND permissions = '{"monthly_plans":"full","invoices":"edit","parts":"view","devices":"view", "bom":"view","orders":"view","statistics":"view","import":"none"}'::jsonb
     ) THEN
    RAISE EXCEPTION 'Откат запрещён: роль employee изменена; старый backend выдаст сотрудникам свои жёстко заданные права.';
  END IF;
END $$;

COMMIT;
