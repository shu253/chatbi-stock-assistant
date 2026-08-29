"""Read-only SQLite access for both model-generated and internal queries."""

from __future__ import annotations

import re
import sqlite3
import time
from collections.abc import Sequence
from pathlib import Path

import pandas as pd
import sqlparse

from .config import Settings, get_settings

ALLOWED_TABLES = frozenset({"stock_daily_price"})
DENIED_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|REPLACE|DROP|ALTER|CREATE|TRIGGER|VACUUM|"
    r"ATTACH|DETACH|PRAGMA|REINDEX|ANALYZE|BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE)\b",
    re.IGNORECASE,
)


class UnsafeQueryError(ValueError):
    """Raised when SQL violates the read-only query policy."""


class QueryExecutionError(RuntimeError):
    """Raised when an otherwise allowed query cannot be completed."""


def validate_read_only_sql(sql: str, *, max_length: int = 10_000) -> str:
    """Validate that SQL contains exactly one read-only SELECT statement."""
    candidate = sql.strip()
    if not candidate:
        raise UnsafeQueryError("SQL 不能为空")
    if len(candidate) > max_length:
        raise UnsafeQueryError(f"SQL 长度不能超过 {max_length} 个字符")

    statements = [part.strip() for part in sqlparse.split(candidate) if part.strip()]
    if len(statements) != 1:
        raise UnsafeQueryError("每次只允许执行一条 SQL")

    statement = sqlparse.parse(statements[0])[0]
    if statement.get_type() != "SELECT":
        raise UnsafeQueryError("只允许 SELECT 或 WITH ... SELECT 查询")

    flattened = " ".join(token.value for token in statement.flatten() if not token.is_whitespace)
    if DENIED_KEYWORDS.search(flattened):
        raise UnsafeQueryError("查询包含被禁止的写入或数据库管理关键字")

    return statements[0].rstrip(";").strip()


def _readonly_uri(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(
            f"数据库不存在：{path}。请先运行数据采集和导入脚本，或复制本地 stock.db。"
        )
    return f"file:{path.resolve().as_posix()}?mode=ro"


def _authorizer(
    action: int, arg1: str | None, _arg2: str | None, _db: str | None, _src: str | None
) -> int:
    """Allow reads from the business table and deny state-changing operations."""
    denied_actions = {
        sqlite3.SQLITE_INSERT,
        sqlite3.SQLITE_UPDATE,
        sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_CREATE_INDEX,
        sqlite3.SQLITE_CREATE_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_INDEX,
        sqlite3.SQLITE_CREATE_TEMP_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_TRIGGER,
        sqlite3.SQLITE_CREATE_TEMP_VIEW,
        sqlite3.SQLITE_CREATE_TRIGGER,
        sqlite3.SQLITE_CREATE_VIEW,
        sqlite3.SQLITE_DROP_INDEX,
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_DROP_TEMP_INDEX,
        sqlite3.SQLITE_DROP_TEMP_TABLE,
        sqlite3.SQLITE_DROP_TEMP_TRIGGER,
        sqlite3.SQLITE_DROP_TEMP_VIEW,
        sqlite3.SQLITE_DROP_TRIGGER,
        sqlite3.SQLITE_DROP_VIEW,
        sqlite3.SQLITE_ALTER_TABLE,
        sqlite3.SQLITE_REINDEX,
        sqlite3.SQLITE_ANALYZE,
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
        sqlite3.SQLITE_PRAGMA,
        sqlite3.SQLITE_TRANSACTION,
        sqlite3.SQLITE_SAVEPOINT,
    }
    if action in denied_actions:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_READ and arg1 not in ALLOWED_TABLES:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def execute_read_query(
    sql: str,
    params: Sequence[object] = (),
    *,
    db_path: Path | None = None,
    settings: Settings | None = None,
) -> pd.DataFrame:
    """Execute a validated query with table allowlisting, timeout and row cap."""
    cfg = settings or get_settings()
    cleaned_sql = validate_read_only_sql(sql, max_length=cfg.max_sql_length)
    target = (db_path or cfg.db_path).resolve()
    deadline = time.monotonic() + cfg.query_timeout_seconds

    try:
        with sqlite3.connect(_readonly_uri(target), uri=True) as connection:
            connection.execute("PRAGMA query_only = ON")
            connection.set_authorizer(_authorizer)
            connection.set_progress_handler(
                lambda: 1 if time.monotonic() > deadline else 0,
                10_000,
            )
            cursor = connection.execute(cleaned_sql, tuple(params))
            if cursor.description is None:
                raise UnsafeQueryError("查询没有返回结果集")
            columns = [item[0] for item in cursor.description]
            rows = cursor.fetchmany(cfg.max_query_rows + 1)
            if len(rows) > cfg.max_query_rows:
                raise QueryExecutionError(
                    f"查询结果超过 {cfg.max_query_rows} 行，请缩小时间范围或增加聚合条件"
                )
            return pd.DataFrame.from_records(rows, columns=columns)
    except (FileNotFoundError, UnsafeQueryError, QueryExecutionError):
        raise
    except sqlite3.DatabaseError as exc:
        message = "查询执行失败或超过时间限制，请检查字段、日期范围和查询复杂度"
        raise QueryExecutionError(message) from exc
