"""Import the downloaded workbook into SQLite."""

from __future__ import annotations

import argparse
from pathlib import Path

from chatbi_stock.data_pipeline import import_excel_to_sqlite


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--excel", type=Path, default=Path("data/stock_prices.xlsx"))
    parser.add_argument("--database", type=Path, default=Path("data/stock.db"))
    parser.add_argument("--schema", type=Path, default=Path("data/schema.sql"))
    args = parser.parse_args()
    total = import_excel_to_sqlite(args.excel, args.database, args.schema)
    print(f"导入完成，数据库共有 {total} 条记录：{args.database}")


if __name__ == "__main__":
    main()
