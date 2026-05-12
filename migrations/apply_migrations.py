"""执行数据库迁移脚本 — 添加 COMMENT 和 FK 约束。

用法:
    python migrations/apply_migrations.py

从 .env 读取 PG_DSN，按文件名顺序执行 migrations/*.sql。
"""

import glob
import os
import sys

import psycopg2
from dotenv import load_dotenv

# Windows 终端 UTF-8 输出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    # 加载项目根目录下的 .env
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(project_root, ".env"))

    dsn = os.getenv("PG_DSN")
    if not dsn:
        print("错误: 未找到 PG_DSN 环境变量，请检查 .env 文件")
        sys.exit(1)

    migration_dir = os.path.dirname(os.path.abspath(__file__))
    sql_files = sorted(glob.glob(os.path.join(migration_dir, "*.sql")))

    if not sql_files:
        print("未找到 SQL 迁移文件")
        sys.exit(0)

    print(f"连接数据库: {dsn.split('@')[1] if '@' in dsn else dsn}")
    try:
        with psycopg2.connect(dsn) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                for sql_file in sql_files:
                    filename = os.path.basename(sql_file)
                    print(f"\n执行: {filename}")
                    with open(sql_file, encoding="utf-8") as f:
                        sql_content = f.read()
                    try:
                        cur.execute(sql_content)
                        print(f"  [OK] {filename} 完成")
                    except Exception as e:
                        print(f"  [FAIL] {filename} 失败: {e}")
                        # 继续执行下一个文件
    except psycopg2.OperationalError as e:
        print(f"\n数据库连接失败: {e}")
        print("请确认 Docker 容器已启动: docker compose up -d")
        sys.exit(1)

    print("\n全部迁移执行完毕")


if __name__ == "__main__":
    main()
