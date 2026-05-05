-- 创建 MCP 桌面 Claude 使用的只读角色
-- 执行：docker compose exec -T postgres psql -U mystock -d mystock_db < backend/db/init_readonly_role.sql

-- 1. 角色（密码请与 .env 中 POSTGRES_RO_PASSWORD 保持一致）
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mystock_readonly') THEN
    CREATE ROLE mystock_readonly WITH LOGIN PASSWORD 'mystock_ro_changeme';
  END IF;
END$$;

-- 2. 库与 schema 权限
GRANT CONNECT ON DATABASE mystock_db TO mystock_readonly;
GRANT USAGE ON SCHEMA public TO mystock_readonly;

-- 3. 现有表只读
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mystock_readonly;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO mystock_readonly;

-- 4. 未来新建表自动只读（跑 migration 后无需重新授权）
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO mystock_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON SEQUENCES TO mystock_readonly;

-- 5. 撤销写权限（保险）
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM mystock_readonly;
