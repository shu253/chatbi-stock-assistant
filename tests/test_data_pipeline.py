from __future__ import annotations

from pathlib import Path

import pandas as pd

from chatbi_stock.data_pipeline import EXPECTED_COLUMNS, import_excel_to_sqlite


def test_excel_import_is_idempotent(tmp_path: Path) -> None:
    workbook = tmp_path / "stocks.xlsx"
    database = tmp_path / "stocks.db"
    schema = tmp_path / "schema.sql"
    schema.write_text(
        """
        CREATE TABLE IF NOT EXISTS stock_daily_price (
          ts_code TEXT NOT NULL, stock_name TEXT NOT NULL, trade_date TEXT NOT NULL,
          open REAL, high REAL, low REAL, close REAL, pre_close REAL, change REAL,
          pct_chg REAL, vol REAL, amount REAL, PRIMARY KEY (ts_code, trade_date)
        );
        """,
        encoding="utf-8",
    )
    row = {
        "ts_code": "600519.SH",
        "stock_name": "贵州茅台",
        "trade_date": "2025-01-02",
        "open": 1,
        "high": 2,
        "low": 1,
        "close": 2,
        "pre_close": 1,
        "change": 1,
        "pct_chg": 100,
        "vol": 10,
        "amount": 20,
    }
    pd.DataFrame([row], columns=EXPECTED_COLUMNS).to_excel(workbook, index=False)
    assert import_excel_to_sqlite(workbook, database, schema) == 1
    assert import_excel_to_sqlite(workbook, database, schema) == 1
