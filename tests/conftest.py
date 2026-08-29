from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture()
def sample_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "sample.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE stock_daily_price (
                ts_code TEXT NOT NULL,
                stock_name TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                pre_close REAL,
                change REAL,
                pct_chg REAL,
                vol REAL,
                amount REAL,
                PRIMARY KEY (ts_code, trade_date)
            );
            """
        )
        rows = [
            (
                "600519.SH",
                "贵州茅台",
                "2025-01-02",
                1500,
                1520,
                1490,
                1510,
                1500,
                10,
                0.67,
                100,
                151000,
            ),
            (
                "600519.SH",
                "贵州茅台",
                "2025-01-03",
                1510,
                1540,
                1505,
                1530,
                1510,
                20,
                1.32,
                120,
                183600,
            ),
            ("000858.SZ", "五粮液", "2025-01-02", 140, 143, 139, 142, 140, 2, 1.43, 500, 71000),
        ]
        connection.executemany(
            "INSERT INTO stock_daily_price VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows
        )
        connection.commit()
    return db_path
