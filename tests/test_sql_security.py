from __future__ import annotations

from pathlib import Path

import pytest

from chatbi_stock.config import Settings
from chatbi_stock.db import (
    QueryExecutionError,
    UnsafeQueryError,
    execute_read_query,
    validate_read_only_sql,
)


def make_settings(db_path: Path, *, max_rows: int = 2_000) -> Settings:
    return Settings(
        dashscope_api_key="",
        tushare_token="",
        tavily_api_key="",
        enable_web_search=False,
        model="qwen-turbo",
        db_path=db_path,
        runtime_dir=db_path.parent / "runtime",
        log_level="INFO",
        max_query_rows=max_rows,
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM stock_daily_price",
        "WITH recent AS (SELECT * FROM stock_daily_price) SELECT COUNT(*) FROM recent",
    ],
)
def test_read_only_select_is_allowed(sql: str) -> None:
    assert validate_read_only_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE stock_daily_price",
        "PRAGMA table_info(stock_daily_price)",
        "UPDATE stock_daily_price SET close = 0",
        "SELECT 1; SELECT 2",
        "ATTACH DATABASE 'other.db' AS other",
    ],
)
def test_unsafe_sql_is_rejected(sql: str) -> None:
    with pytest.raises(UnsafeQueryError):
        validate_read_only_sql(sql)


def test_query_executes_against_allowed_table(sample_db: Path) -> None:
    result = execute_read_query(
        "SELECT stock_name, ROUND(AVG(close), 2) AS avg_close "
        "FROM stock_daily_price GROUP BY stock_name ORDER BY stock_name",
        settings=make_settings(sample_db),
    )
    assert result.shape == (2, 2)
    assert set(result["stock_name"]) == {"贵州茅台", "五粮液"}


def test_parameterized_internal_query(sample_db: Path) -> None:
    result = execute_read_query(
        "SELECT close FROM stock_daily_price WHERE ts_code = ? ORDER BY trade_date",
        ("600519.SH",),
        settings=make_settings(sample_db),
    )
    assert result["close"].tolist() == [1510.0, 1530.0]


def test_row_cap_prevents_unbounded_result(sample_db: Path) -> None:
    with pytest.raises(QueryExecutionError, match="超过 1 行"):
        execute_read_query(
            "SELECT * FROM stock_daily_price",
            settings=make_settings(sample_db, max_rows=1),
        )


def test_unknown_table_is_denied(sample_db: Path) -> None:
    with pytest.raises(QueryExecutionError):
        execute_read_query(
            "SELECT * FROM sqlite_master",
            settings=make_settings(sample_db),
        )
