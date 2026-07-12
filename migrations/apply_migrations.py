"""执行数据库迁移脚本。

用法:
    python migrations/apply_migrations.py                       # 应用未记录迁移
    python migrations/apply_migrations.py --bootstrap-existing  # 一次性把已存在
                                                          001-010 schema 记入
                                                          ledger，不重跑

迁移以独立事务顺序执行，并写入 ``schema_migrations(filename, checksum, applied_at)``
ledger。任何迁移失败或已记录迁移 checksum 漂移都会立刻非零退出；ledger 存在的
数据库不能再次使用 ``--bootstrap-existing``，否则会拒绝执行。

``schema_migrations.checksum`` 为 SHA-256(filename || "\\n" || sql_content)，修改
已应用迁移的唯一合法方式是新增下一编号文件。
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import os
import sys

import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# 001-010 已发布迁移的代表性表/列/约束哨兵；只有全部存在才允许 bootstrap。
# 每个条目: (table_name, required_columns_optional) 或 (table_name, column_name)。
# False 表示该表存在即可，True 表示还必须包含该列。
BOOTSTRAP_SENTINELS: list[tuple[str, bool]] = [
    ("task_runs", False),
    ("source_documents", False),
    ("competitors", False),
    ("competitor_products", False),
    ("intel_facts", False),
    ("insight_claims", False),
    ("evidence_refs", False),
    ("analysis_reports", False),
    ("source_profiles", False),
    ("document_clusters", False),
    ("source_occurrences", False),
    ("source_document_versions", False),
    ("intel_facts", "assertion_key"),
    ("intel_facts", "verification_status"),
    ("evidence_refs", "document_version_id"),
    ("evidence_refs", "source_occurrence_id"),
    ("analysis_reports", "review_status"),
    ("analysis_reports", "quality_score"),
    ("source_occurrences", "shingles"),
]


def _print(msg: str) -> None:
    print(msg)


def _compute_checksum(filename: str, sql_content: str) -> str:
    h = hashlib.sha256()
    h.update(filename.encode("utf-8"))
    h.update(b"\n")
    h.update(sql_content.encode("utf-8"))
    return h.hexdigest()


def _ensure_ledger(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename   TEXT PRIMARY KEY,
            checksum   TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _get_applied(cur) -> dict[str, str]:
    cur.execute("SELECT filename, checksum FROM schema_migrations")
    return {row[0]: row[1] for row in cur.fetchall()}


def _verify_bootstrap_sentinels(cur) -> list[str]:
    """返回不满足的 sentinel 列表；空列表表示全部匹配。"""
    missing: list[str] = []
    for table, require_column in BOOTSTRAP_SENTINELS:
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
            (table,),
        )
        if cur.fetchone() is None:
            missing.append(f"missing table {table}")
            continue
        if require_column:
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s
                """,
                (table, require_column),
            )
            if cur.fetchone() is None:
                missing.append(f"missing column {table}.{require_column}")
    return missing


def _record_applied(cur, filename: str, checksum: str) -> None:
    cur.execute(
        "INSERT INTO schema_migrations (filename, checksum) VALUES (%s, %s)",
        (filename, checksum),
    )


def _run_in_transaction(conn, sql_content: str) -> None:
    """单文件失败即整体回滚并抛错，由调用方决定退出。"""
    with conn.cursor() as cur:
        cur.execute(sql_content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="应用 PostgreSQL 迁移脚本")
    parser.add_argument(
        "--bootstrap-existing",
        action="store_true",
        help="一次性把已存在 001-010 schema 记入 ledger，不重跑迁移",
    )
    args = parser.parse_args(argv)

    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    dsn = os.getenv("PG_DSN")
    if not dsn:
        _print("错误: 未找到 PG_DSN 环境变量，请检查 .env 文件")
        return 1

    migration_dir = os.path.dirname(os.path.abspath(__file__))
    sql_files = sorted(glob.glob(os.path.join(migration_dir, "*.sql")))
    if not sql_files:
        _print("未找到 SQL 迁移文件")
        return 0

    _print(f"连接数据库: {dsn.split('@')[1] if '@' in dsn else dsn}")

    try:
        with psycopg2.connect(dsn) as conn:
            conn.autocommit = False
            with conn.cursor() as cur:
                _ensure_ledger(cur)
                conn.commit()

                applied = _get_applied(cur)

                if args.bootstrap_existing:
                    if applied:
                        _print(
                            "[FAIL] --bootstrap-existing 只能在 ledger 为空时使用。"
                            f"当前已记录 {len(applied)} 个迁移。"
                        )
                        return 2
                    missing = _verify_bootstrap_sentinels(cur)
                    if missing:
                        _print("[FAIL] 数据库结构不满足 bootstrap 哨兵:")
                        for item in missing:
                            _print(f"  - {item}")
                        return 3
                    # 现有 001-010 schema 视作已应用，记录 checksum 但不重跑。
                    recorded = 0
                    for sql_file in sql_files:
                        filename = os.path.basename(sql_file)
                        prefix = filename.split("_", 1)[0]
                        if not prefix.isdigit() or int(prefix) > 10:
                            continue
                        with open(sql_file, encoding="utf-8") as f:
                            sql_content = f.read()
                        checksum = _compute_checksum(filename, sql_content)
                        _record_applied(cur, filename, checksum)
                        recorded += 1
                    conn.commit()
                    _print(f"[OK] bootstrap 已记录 {recorded} 个历史迁移")
                    return 0

                # 校验已记录迁移的 checksum，未变化才继续
                drift: list[str] = []
                for sql_file in sql_files:
                    filename = os.path.basename(sql_file)
                    if filename not in applied:
                        continue
                    with open(sql_file, encoding="utf-8") as f:
                        sql_content = f.read()
                    expected = _compute_checksum(filename, sql_content)
                    if applied[filename] != expected:
                        drift.append(filename)
                if drift:
                    _print("[FAIL] 已记录迁移的 checksum 与当前文件不一致:")
                    for filename in drift:
                        _print(f"  - {filename}")
                    _print("修正方式: 新增下一编号迁移文件，不要原地修改已应用迁移。")
                    return 4

                pending = 0
                for sql_file in sql_files:
                    filename = os.path.basename(sql_file)
                    if filename in applied:
                        continue
                    pending += 1

                if pending == 0:
                    _print("没有待执行迁移。")
                    return 0

                for sql_file in sql_files:
                    filename = os.path.basename(sql_file)
                    if filename in applied:
                        continue
                    _print(f"应用: {filename}")
                    with open(sql_file, encoding="utf-8") as f:
                        sql_content = f.read()
                    try:
                        _run_in_transaction(conn, sql_content)
                    except Exception as exc:
                        conn.rollback()
                        _print(f"  [FAIL] {filename}: {exc}")
                        _print("迁移失败，已回滚。修复后重跑。")
                        return 5
                    checksum = _compute_checksum(filename, sql_content)
                    _record_applied(cur, filename, checksum)
                    conn.commit()
                    _print(f"  [OK] {filename} 完成")

                _print("全部待执行迁移已应用。")
                return 0

    except psycopg2.OperationalError as exc:
        _print(f"\n数据库连接失败: {exc}")
        _print("请确认 Docker 容器已启动: docker compose up -d")
        return 1


if __name__ == "__main__":
    sys.exit(main())