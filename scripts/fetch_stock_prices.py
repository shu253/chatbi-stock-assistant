"""Download the configured stock universe from Tushare."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from chatbi_stock.data_pipeline import fetch_stock_prices


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/stock_prices.xlsx"))
    parser.add_argument("--start-date", default="20200101")
    parser.add_argument("--end-date", default=None)
    args = parser.parse_args()
    count = fetch_stock_prices(
        os.getenv("TUSHARE_TOKEN", ""),
        args.output,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(f"已保存 {count} 条行情数据到 {args.output}")


if __name__ == "__main__":
    main()
