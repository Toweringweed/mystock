# 桌面版 Claude + PostgreSQL MCP 接入指南

让桌面版 Claude 直接查询 MyStock 数据库做交互分析。

## 步骤 1：创建只读角色

```bash
cd /Volumes/data/mystock
docker compose exec -T postgres psql -U mystock -d mystock_db < backend/db/init_readonly_role.sql
```

如果想改默认密码，先编辑 `backend/db/init_readonly_role.sql` 中的 `mystock_ro_changeme`。

验证：

```bash
# 应能 SELECT
docker compose exec postgres psql -U mystock_readonly -d mystock_db \
  -c "SELECT count(*) FROM stocks"

# 应被拒绝
docker compose exec postgres psql -U mystock_readonly -d mystock_db \
  -c "DELETE FROM stocks"
```

## 步骤 2：配置桌面 Claude

文件路径（macOS）：

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

如不存在则新建。在 `mcpServers` 下添加：

```json
{
  "mcpServers": {
    "mystock-pg": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-postgres",
        "postgresql://mystock_readonly:mystock_ro_changeme@localhost:5432/mystock_db"
      ]
    }
  }
}
```

如果你也用其他 MCP server，把 `mystock-pg` 加到 `mcpServers` 里即可，不要替换其他条目。

## 步骤 3：把数据字典加为知识库

在桌面版 Claude 的 Project（项目）里上传或粘贴 `docs/mcp-data-dictionary.md` 全文作为项目知识，让它每次对话默认带上字段含义和查询模式。

## 步骤 4：重启桌面 Claude

退出 → 重新打开。在新对话开始时，应能看到 `mystock-pg` 工具可用。

## 步骤 5：试用

```
我自选股里 PE-TTM 最低的 5 只是哪些？给我每只最近一份 AI 报告的结论。
```

```
今天有哪些股触发了事件？按 severity 排序。
```

```
我自选股里有 MACD 底背离 + PE 处于近 5 年 30% 分位以下的股票吗？
```

## 常见问题

**Q：连不上数据库**

A：确保 docker compose 在跑（`docker compose ps`），且 postgres 端口 5432 已映射到主机（`docker-compose.yml` 已配置）。

**Q：看不到 mystock-pg 工具**

A：完全退出桌面 Claude（不只是关闭窗口），用 Activity Monitor 确认进程已退出，再重新打开。

**Q：API Key 会不会泄漏**

A：`mystock_readonly` 角色虽然只读，但数据字典已提示 Claude 不要 SELECT `app_settings`。如果想从数据库层彻底隔离，可补一条：

```sql
REVOKE SELECT ON app_settings FROM mystock_readonly;
```
