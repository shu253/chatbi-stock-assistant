"""Reusable stock-data download and SQLite import operations."""

from __future__ import annotations

import sqlite3
import time
from datetime import date
from pathlib import Path

import pandas as pd

STOCKS = {
    "600519.SH": "贵州茅台",
    "000858.SZ": "五粮液",
    "600838.SH": "上海九百",
    "688981.SH": "中芯国际",
}
EXPECTED_COLUMNS = [
    "ts_code",
    "stock_name",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change",
    "pct_chg",
    "vol",
    "amount",
]


def fetch_stock_prices(
    token: str,
    output_file: Path,
    *,
    start_date: str = "20200101",
    end_date: str | None = None,
) -> int:
    if not token:
        raise ValueError("TUSHARE_TOKEN 不能为空")
    import tushare as ts

    ts.set_token(token)
    client = ts.pro_api()
    frames: list[pd.DataFrame] = []
    target_end = end_date or date.today().strftime("%Y%m%d")
    for index, (stock_code, stock_name) in enumerate(STOCKS.items()):
        frame = client.daily(ts_code=stock_code, start_date=start_date, end_date=target_end)
        if frame is not None and not frame.empty:
            frame["stock_name"] = stock_name
            frames.append(frame)
        if index < len(STOCKS) - 1:
            time.sleep(0.3)
    if not frames:
        raise RuntimeError("未获取到行情数据，请检查 Token、网络或接口权限")

    combined = pd.concat(frames, ignore_index=True)
    combined["trade_date"] = pd.to_datetime(combined["trade_date"], format="%Y%m%d")
    combined = combined.sort_values(["trade_date", "ts_code"])
    combined = combined[EXPECTED_COLUMNS]
    output_file.parent.mkdir(parents=True, exist_ok=True)
    combined.to_excel(output_file, sheet_name="历史价格", index=False, engine="openpyxl")
    return len(combined)


def import_excel_to_sqlite(excel_file: Path, db_file: Path, schema_file: Path) -> int:
    frame = pd.read_excel(excel_file)
    missing = [column for column in EXPECTED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Excel 缺少字段：{missing}")
    frame = frame[EXPECTED_COLUMNS].copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.strftime("%Y-%m-%d")

    db_file.parent.mkdir(parents=True, exist_ok=True)
    schema = schema_file.read_text(encoding="utf-8")
    columns = ",".join(EXPECTED_COLUMNS)
    placeholders = ",".join("?" for _ in EXPECTED_COLUMNS)
    insert_sql = f"INSERT OR REPLACE INTO stock_daily_price ({columns}) VALUES ({placeholders})"
    with sqlite3.connect(db_file) as connection:
        connection.executescript(schema)
        connection.executemany(insert_sql, frame.itertuples(index=False, name=None))
        connection.commit()
        total = connection.execute("SELECT COUNT(*) FROM stock_daily_price").fetchone()[0]
    return int(total)
