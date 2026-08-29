# 数据来源与发布说明

仓库公开提供以下演示数据：

- `data/stock_prices.xlsx`：Excel 格式的完整日线行情；
- `data/stock.db`：应用可直接查询的 SQLite 数据库。

数据通过 Tushare API 获取，覆盖贵州茅台、五粮液、上海九百和中芯国际，当前共
6,318 条记录，日期范围为 2020-01-02 至 2026-08-27。

本仓库的 MIT License 仅覆盖源代码，不自动覆盖第三方行情数据。数据使用者应自行
确认数据供应商最新的授权范围、署名要求和再分发条件；数据仅用于项目演示、学习与
技术验证，不构成证券研究或投资建议。

如需更新数据，可使用自己的 `TUSHARE_TOKEN` 运行：

```powershell
python scripts/fetch_stock_prices.py
python scripts/import_to_sqlite.py
```
