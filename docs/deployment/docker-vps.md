# VPS Docker Compose 部署

本文档描述单台 VPS 上的生产部署方式。当前方案默认全新数据库，不保留旧 PostgreSQL/Qdrant/Redis 数据。

## 架构

生产部署由 `docker-compose.prod.yml` 编排：

| 服务 | 说明 |
|---|---|
| `caddy` | 唯一公网入口，监听 80/443，启用 Basic Auth，反向代理到 `web:8005` |
| `web` | FastAPI API + Vue 静态资源 |
| `worker` | Celery Worker，执行 Pipeline、简报、报告等异步任务 |
| `beat` | Celery Beat，定时投递任务 |
| `migrate` | 一次性执行 SQL migration 和健康检查 |
| `postgres` | PostgreSQL 16，保存权威文档、父块、全文索引、point 状态、竞品和报告 |
| `redis` | Celery Broker / Result Backend，启用密码和 AOF |
| `qdrant` | 子块向量、正文 payload 和检索 metadata |

生产环境只发布 Caddy 的 80/443。PostgreSQL、Redis、Qdrant、Web、Worker、Beat 均不发布公网端口。

## 首次部署

1. 准备 VPS：

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin git
sudo systemctl enable --now docker
```

2. 拉取代码并创建配置：

```bash
git clone <your-repo-url> Logos
cd Logos
cp .env.deploy.example .env
```

生产 compose 使用显式环境变量映射；`web/worker/beat/migrate` 的运行环境来自 `.env`，同时把 `.env` 挂载到 `/app/.env`，用于配置 API 的持久化写入。提交前或改配置后可先校验示例配置：

```bash
BASIC_AUTH_HASH=dummy docker compose --env-file .env.deploy.example -f docker-compose.prod.yml config
```

3. 生成 Basic Auth 密码哈希：

```bash
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'change-me'
```

把输出替换 `.env` 的 `BASIC_AUTH_HASH=REPLACE_WITH_CADDY_HASH`。建议用单引号包住哈希，避免 `$` 被 shell 解析。

4. 编辑 `.env`：

```bash
CADDY_DOMAIN=logos.example.com
BASIC_AUTH_USER=admin
BASIC_AUTH_HASH=<caddy hash>
POSTGRES_PASSWORD=<strong-password>
REDIS_PASSWORD=<strong-redis-password>
PG_DSN=postgresql://postgres:<strong-password>@postgres:5432/logos
CELERY_BROKER_URL=redis://:<strong-redis-password>@redis:6379/0
CELERY_RESULT_BACKEND=redis://:<strong-redis-password>@redis:6379/0
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=
QDRANT_DOCUMENTS_COLLECTION=insightforge_documents_v1
QDRANT_DISTANCE=Cosine
VECTOR_BACKEND=qdrant
APP_ENV=production
AUTH_ENABLED=true
REPORT_QUALITY_AUTO_PUBLISH=false
```

同时填写 LLM、Embedding、结构化抽取、Judge、NewsAPI、Tavily 等业务配置。若暂时没有域名，可使用 `CADDY_DOMAIN=:80` 做 HTTP 冒烟测试。

5. 启动：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

6. 创建应用级 admin API Key：

```bash
docker compose -f docker-compose.prod.yml run --rm web \
  python -m delivery.cli auth create-key --name initial-admin --role admin
```

命令输出的明文 key 只显示一次。Caddy Basic Auth 是入口防线，应用 API Key 是后端权限控制；前端登录时使用应用 API Key。

7. 查看状态：

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f web
```

## 验证

部署前静态校验：

```bash
BASIC_AUTH_HASH=dummy docker compose --env-file .env.deploy.example -f docker-compose.prod.yml config
```

未带 Basic Auth 访问应返回 401：

```bash
curl -i http://localhost/api/health
```

带 Basic Auth 访问应返回健康检查 JSON：

```bash
curl -u admin:change-me http://localhost/api/health
```

`/api/health` 不要求应用 API Key，但返回内容会脱敏，只包含 PostgreSQL、Redis、Qdrant、auth 和 config 的 readiness。生产环境如果 `AUTH_ENABLED=false` 会返回 unhealthy。

带 Basic Auth 但不带应用 API Key 访问敏感 API 应返回 401；带 viewer key 调用报告生成、配置修改、Webhook 管理等写操作应返回 403。admin key 创建后，应优先验证：

```bash
curl -u admin:change-me -H "Authorization: Bearer <admin-api-key>" http://localhost/api/auth/me
```

报告治理 smoke 验收建议依次覆盖：

- analyst key 调用 `POST /api/reports/generate`，质量通过时应返回 `waiting_review/passed`，质量失败时应返回 `revision_required/failed`。
- viewer key 调用报告生成、配置修改或发布接口应返回 403。
- admin key 调用 `POST /api/reports/{report_id}/approve` 后，再调用 `POST /api/reports/{report_id}/publish`，只有 `approved + passed` 报告可发布。
- admin key 调用 `GET /api/config` 应看到 secret 脱敏值；调用 `PUT /api/config` 或 `POST /api/config/reload` 后，`GET /api/config/audit` 应出现对应审计记录。

浏览器访问 `https://logos.example.com`，输入 Basic Auth 后应加载 Vue 前端。

## 备份

备份 PostgreSQL：

```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U postgres -d logos > logos_$(date +%Y%m%d_%H%M%S).sql
```

备份 Qdrant volume 建议在停机窗口进行：

```bash
docker compose -f docker-compose.prod.yml stop qdrant
docker run --rm -v logos_qdrant_data:/qdrant/storage -v "$PWD":/backup alpine \
  tar czf /backup/qdrant_data_$(date +%Y%m%d_%H%M%S).tar.gz -C /qdrant/storage .
docker compose -f docker-compose.prod.yml start qdrant
```

备份运行时配置和文件：

```bash
cp .env .env.backup
docker run --rm -v logos_logos_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/logos_data_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .
docker run --rm -v logos_logos_output:/output -v "$PWD":/backup alpine \
  tar czf /backup/logos_output_$(date +%Y%m%d_%H%M%S).tar.gz -C /output .
```

卷名前缀通常来自目录名；如果目录名不是 `Logos`，用 `docker volume ls` 确认实际名称。

## 恢复

恢复 PostgreSQL：

```bash
docker compose -f docker-compose.prod.yml stop web worker beat
cat logos_YYYYMMDD_HHMMSS.sql | docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U postgres -d logos
docker compose -f docker-compose.prod.yml up -d web worker beat
```

恢复 Qdrant 或运行时文件建议在停机窗口执行，先停止对应服务和依赖服务，再解压备份到对应 Docker volume。恢复后访问 `/api/health` 确认组件状态。

## 升级

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

`migrate` 会在 `web`、`worker`、`beat` 启动前运行。迁移脚本可重复执行。

升级失败回滚：

```bash
git checkout <last-known-good-commit>
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f web
```

如果迁移已经改变数据库，先恢复升级前 PostgreSQL 备份，再回滚镜像。

## Redis 密码轮换

1. 生成新 `REDIS_PASSWORD`。
2. 同步更新 `.env` 中 `REDIS_PASSWORD`、`CELERY_BROKER_URL` 和 `CELERY_RESULT_BACKEND`。
3. 重启 Redis、web、worker、beat：

```bash
docker compose -f docker-compose.prod.yml up -d redis web worker beat
```

4. 访问 `/api/health`，确认 Redis readiness 为 ok。

## 清空重建

如果要按全新环境重来：

```bash
docker compose -f docker-compose.prod.yml down -v
docker compose -f docker-compose.prod.yml up -d --build
```

`down -v` 会删除 PostgreSQL、Redis、Qdrant、Caddy、`data`、`output` 等所有 Docker volumes。确认不需要保留数据后再执行。
