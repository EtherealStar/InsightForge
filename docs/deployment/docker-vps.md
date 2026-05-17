# VPS Docker Compose 部署

本文档描述单台 VPS 上的生产部署方式。该方案默认全新数据库，不保留本地现有 PostgreSQL 数据。

## 架构

生产部署由 `docker-compose.prod.yml` 编排：

| 服务 | 说明 |
|---|---|
| `caddy` | 唯一公网入口，监听 80/443，启用 Basic Auth，反向代理到 `web:8005` |
| `web` | FastAPI API + Vue 静态资源 |
| `worker` | Celery Worker，执行 Pipeline、简报、清理等异步任务 |
| `beat` | Celery Beat，定时投递任务 |
| `migrate` | 一次性初始化空数据库 schema 并执行 `migrations/*.sql` |
| `postgres` | PostgreSQL 16 + pgvector |
| `redis` | Celery Broker / Result Backend |
| `flower` | 可选任务监控，需 `monitoring` profile |

PostgreSQL、Redis、Web、Worker、Beat 不发布公网端口；公网只访问 Caddy。

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

3. 生成 Basic Auth 密码哈希：

```bash
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'change-me'
```

把输出写入 `.env` 的 `BASIC_AUTH_HASH`。建议用单引号包住哈希，避免 `$` 被解析，例如 `BASIC_AUTH_HASH='$2a$14$...'`。

4. 编辑 `.env`：

```bash
CADDY_DOMAIN=logos.example.com
BASIC_AUTH_USER=admin
BASIC_AUTH_HASH=<caddy hash>
POSTGRES_PASSWORD=<strong-password>
PG_DSN=postgresql://postgres:<strong-password>@postgres:5432/logos
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
```

同时填写 LLM、Embedding、NewsAPI、Tavily 等业务配置。若暂时没有域名，可使用 `CADDY_DOMAIN=:80` 做 HTTP 冒烟测试。

5. 启动：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

默认读取仓库根目录 `.env`。如需在不覆盖本地 `.env` 的情况下验证另一份配置，可设置 `LOGOS_ENV_FILE=.env.deploy.example`，但生产部署建议使用 `.env`。

6. 查看状态：

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f web
```

## 验证

未带 Basic Auth 访问应返回 401：

```bash
curl -i http://localhost/api/health
```

带 Basic Auth 访问应返回健康检查 JSON：

```bash
curl -u admin:change-me http://localhost/api/health
```

浏览器访问 `https://logos.example.com`，输入 Basic Auth 后应加载 Vue 前端。

## 可选 Flower

Flower 默认不启动。如需临时查看 Celery：

```bash
docker compose -f docker-compose.prod.yml --profile monitoring up -d flower
```

如需公网访问 Flower，请优先通过 SSH tunnel 或额外受保护的反向代理暴露，不要直接发布端口。

## 备份

备份 PostgreSQL：

```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U postgres -d logos > logos_$(date +%Y%m%d_%H%M%S).sql
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

## 升级

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

`migrate` 会在 `web`、`worker`、`beat` 启动前运行。迁移脚本可重复执行。

## 清空重建

如果要按全新环境重来：

```bash
docker compose -f docker-compose.prod.yml down -v
docker compose -f docker-compose.prod.yml up -d --build
```

`down -v` 会删除 PostgreSQL、Redis、Caddy、`data`、`output` 等所有 Docker volumes。确认不需要保留数据后再执行。
