-- MyStock 只读角色初始化
-- 供 Claude Code MCP (mystock-pg) 连接使用

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mystock_readonly') THEN
    CREATE ROLE mystock_readonly WITH LOGIN PASSWORD 'mystock_ro_changeme';
  ELSE
    ALTER ROLE mystock_readonly WITH PASSWORD 'mystock_ro_changeme';
  END IF;
END$$;

GRANT CONNECT ON DATABASE mystock_db TO mystock_readonly;
GRANT USAGE ON SCHEMA public TO mystock_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mystock_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO mystock_readonly;
