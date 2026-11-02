"""迁移 runner。

Python 端不新增迁移版本，直接执行 Go 仓库已有的 SQL：
- postgres: `migrations/versioned/*.up.sql`（按 000000 → 000122 顺序）
- sqlite:   `migrations/sqlite/*.up.sql`（Lite 模式的合并版 schema）

已执行版本记录在 `schema_migrations` 表，保证幂等。
"""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote_plus

from app.core.config import REPO_ROOT, Settings

logger = logging.getLogger(__name__)

VERSIONED_DIR = REPO_ROOT / "migrations" / "versioned"
SQLITE_DIR = REPO_ROOT / "migrations" / "sqlite"


def _sql_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.up.sql"))


def _version_of(path: Path) -> str:
    return path.name.removesuffix(".up.sql")


async def run_migrations(settings: Settings) -> None:
    if settings.db_driver.lower() == "sqlite":
        await _run_sqlite(settings)
    else:
        await _run_postgres(settings)


async def _run_postgres(settings: Settings) -> None:
    import asyncpg

    files = _sql_files(VERSIONED_DIR)
    if not files:
        logger.warning("no postgres migrations found at %s", VERSIONED_DIR)
        return

    dsn = (
        f"postgresql://{quote_plus(settings.db_user)}:{quote_plus(settings.db_password)}"
        f"@{settings.db_host}:{settings.db_port}/{settings.db_name}"
    )
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version VARCHAR(128) PRIMARY KEY, "
            "applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
        )
        rows = await conn.fetch("SELECT version FROM schema_migrations")
        applied = {row["version"] for row in rows}
        for path in files:
            version = _version_of(path)
            if version in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            async with conn.transaction():
                # asyncpg 无参数时走简单协议，支持一次执行多语句。
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations(version) VALUES($1) "
                    "ON CONFLICT (version) DO NOTHING",
                    version,
                )
            logger.info("applied migration %s", version)
    finally:
        await conn.close()


async def _run_sqlite(settings: Settings) -> None:
    import aiosqlite

    files = _sql_files(SQLITE_DIR)
    if not files:
        logger.warning("no sqlite migrations found at %s", SQLITE_DIR)
        return

    db_path = settings.sqlite_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, "
            "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        cursor = await conn.execute("SELECT version FROM schema_migrations")
        applied = {row[0] for row in await cursor.fetchall()}
        for path in files:
            version = _version_of(path)
            if version in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            await conn.executescript(sql)
            await conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)", (version,)
            )
            await conn.commit()
            logger.info("applied migration %s", version)
