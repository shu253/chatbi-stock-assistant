# 数据来源与发布说明

项目的数据采集脚本通过 Tushare API 获取证券日线行情。仓库默认不提交本地 Excel、SQLite 数据库和 API Token。

公开发布完整行情数据前，请项目维护者自行确认数据供应商最新的授权范围、署名要求和再分发条件。本仓库的 MIT License 仅覆盖源代码，不自动覆盖第三方数据。

推荐使用方式：

1. 使用自己的 `TUSHARE_TOKEN` 运行 `scripts/fetch_stock_prices.py`；
2. 运行 `scripts/import_to_sqlite.py` 构建本地数据库；
3. 将生成的 `data/*.xlsx` 和 `data/*.db` 保持在 Git 忽略列表中。

