"""Qwen Agent tool implementations for SQL, ARIMA and BOLL analysis."""

from __future__ import annotations

import json
import logging
import warnings
from datetime import datetime, timedelta

import pandas as pd
from qwen_agent.tools.base import BaseTool, register_tool

from .analytics import calculate_bollinger_bands, detect_bollinger_breakouts
from .charts import (
    allocate_image_path,
    cleanup_runtime_images,
    markdown_image_path,
    plot_bollinger,
    plot_forecast,
    plot_query_result,
)
from .config import PROJECT_ROOT, get_settings
from .db import QueryExecutionError, UnsafeQueryError, execute_read_query

LOGGER = logging.getLogger(__name__)
ARIMA_ORDER = (5, 1, 5)
ARIMA_HISTORY_DAYS = 365
BOLL_WINDOW = 20
BOLL_STD_MULTIPLIER = 2.0
BOLL_DEFAULT_DAYS = 365
BOLL_LOOKBACK_DAYS = 60


def _prepare_runtime() -> None:
    settings = get_settings()
    cleanup_runtime_images(
        settings.runtime_dir,
        retention_hours=settings.image_retention_hours,
        retention_count=settings.image_retention_count,
    )


def _image_markdown(path, alt: str) -> str:
    return f"![{alt}]({markdown_image_path(path, PROJECT_ROOT)})"


def _resolve_stock(stock: str) -> tuple[str, str]:
    rows = execute_read_query(
        "SELECT DISTINCT ts_code, stock_name FROM stock_daily_price ORDER BY ts_code"
    )
    code_to_name = dict(zip(rows["ts_code"], rows["stock_name"], strict=True))
    name_to_code = {name: code for code, name in code_to_name.items()}
    if stock in code_to_name:
        return stock, code_to_name[stock]
    if stock in name_to_code:
        return name_to_code[stock], stock
    supported = "、".join(f"{name}（{code}）" for code, name in code_to_name.items())
    raise ValueError(f"股票 {stock} 不在数据库中。当前支持：{supported}")


@register_tool("exc_sql")
class ExcSQLTool(BaseTool):
    description = "执行只读 SQLite 查询，并根据结果生成表格和可视化"
    parameters = [
        {
            "name": "sql_input",
            "type": "string",
            "description": "单条 SELECT 或 WITH ... SELECT 查询",
            "required": True,
        }
    ]

    def call(self, params: str, **kwargs) -> str:
        del kwargs
        try:
            args = json.loads(params)
            frame = execute_read_query(str(args["sql_input"]))
        except (json.JSONDecodeError, KeyError):
            return "SQL 工具参数格式不正确"
        except (UnsafeQueryError, QueryExecutionError, FileNotFoundError) as exc:
            return f"查询被拒绝：{exc}"

        if "trade_date" in frame.columns and len(frame) > 1:
            frame = frame.sort_values("trade_date").reset_index(drop=True)
        if frame.empty:
            return "查询成功，但当前条件下没有数据"
        if len(frame) == 1:
            return "\n".join(f"{column}: {value}" for column, value in frame.iloc[0].items())

        if len(frame) <= 20:
            sections = [frame.to_markdown(index=False)]
        else:
            sections = [
                f"## 数据集概览（共 {len(frame)} 行，展示前 5 行和后 5 行）",
                f"### 前 5 行\n{frame.head(5).to_markdown(index=False)}",
                f"### 后 5 行\n{frame.tail(5).to_markdown(index=False)}",
            ]
        numeric = frame.select_dtypes(include="number")
        if not numeric.empty:
            sections.append(f"### 数值列描述统计\n{numeric.describe().round(2).to_markdown()}")

        try:
            _prepare_runtime()
            settings = get_settings()
            image_path = allocate_image_path(settings.runtime_dir, "query")
            plot_query_result(frame, image_path)
            sections.append(_image_markdown(image_path, "查询结果图表"))
        except (TypeError, ValueError) as exc:
            LOGGER.info("查询结果不适合自动绘图：%s", exc)
        return "\n\n".join(sections)


@register_tool("arima_stock")
class ArimaStockTool(BaseTool):
    description = "基于最近一年收盘价使用 ARIMA(5,1,5) 预测未来工作日价格"
    parameters = [
        {
            "name": "ts_code",
            "type": "string",
            "description": "数据库内的股票代码或名称",
            "required": True,
        },
        {
            "name": "n",
            "type": "integer",
            "description": "预测工作日数量，默认 5，最大 30",
            "required": False,
        },
    ]

    def call(self, params: str, **kwargs) -> str:
        del kwargs
        try:
            args = json.loads(params)
            stock_code, stock_name = _resolve_stock(str(args["ts_code"]).strip())
            days = int(args.get("n", 5))
            if not 1 <= days <= 30:
                return "预测天数必须在 1 到 30 之间"
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            return str(exc)

        latest = execute_read_query(
            "SELECT MAX(trade_date) AS latest_date FROM stock_daily_price WHERE ts_code = ?",
            (stock_code,),
        ).iloc[0, 0]
        if not latest:
            return f"未找到 {stock_name} 的历史数据"
        end_date = datetime.strptime(str(latest), "%Y-%m-%d")
        start_date = (end_date - timedelta(days=ARIMA_HISTORY_DAYS)).strftime("%Y-%m-%d")
        history = execute_read_query(
            "SELECT ts_code, stock_name, trade_date, close FROM stock_daily_price "
            "WHERE ts_code = ? AND trade_date >= ? AND trade_date <= ? ORDER BY trade_date",
            (stock_code, start_date, latest),
        )
        if len(history) < 60:
            return f"历史数据不足（仅 {len(history)} 条），无法进行 ARIMA 建模"

        try:
            from statsmodels.tsa.arima.model import ARIMA

            model = ARIMA(history["close"].astype(float), order=ARIMA_ORDER)
            with warnings.catch_warnings(record=True) as model_warnings:
                warnings.simplefilter("always")
                fitted = model.fit()
            forecast = fitted.forecast(steps=days)
        except Exception as exc:  # statsmodels exposes several model-specific exceptions
            LOGGER.exception("ARIMA 建模失败")
            return f"ARIMA 建模未成功：{type(exc).__name__}"

        warning_names = {type(item.message).__name__ for item in model_warnings}
        converged = bool(getattr(fitted, "mle_retvals", {}).get("converged", True))
        if warning_names:
            LOGGER.warning("ARIMA 建模警告：%s", ", ".join(sorted(warning_names)))
        stability_note = (
            "- **稳定性提示**：本次模型优化未完全收敛，预测不确定性较高"
            if not converged
            else "- **稳定性提示**：模型已完成拟合，但历史拟合不代表未来准确性"
        )

        forecast_dates = (
            pd.bdate_range(start=end_date + timedelta(days=1), periods=days)
            .strftime("%Y-%m-%d")
            .tolist()
        )
        result = pd.DataFrame(
            {"预测日期（工作日近似）": forecast_dates, "预测收盘价": forecast.round(2).tolist()}
        )
        _prepare_runtime()
        settings = get_settings()
        image_path = allocate_image_path(
            settings.runtime_dir, f"arima_{stock_code.replace('.', '_')}"
        )
        plot_forecast(
            history,
            forecast,
            forecast_dates,
            stock_code=stock_code,
            stock_name=stock_name,
            save_path=image_path,
        )
        history_summary = (
            f"- **建模数据**：{history.iloc[0]['trade_date']} 至 "
            f"{history.iloc[-1]['trade_date']}，共 {len(history)} 个交易日"
        )
        return "\n\n".join(
            [
                f"## ARIMA{ARIMA_ORDER} 价格预测",
                f"- **股票**：{stock_name}（{stock_code}）",
                history_summary,
                "- **日期说明**：未来日期按工作日近似，未完整排除交易所休市日",
                stability_note,
                f"### 预测结果\n{result.to_markdown(index=False)}",
                _image_markdown(image_path, "ARIMA 预测图"),
                "以上结果仅供技术演示，不构成投资建议。",
            ]
        )


@register_tool("boll_detection")
class BollDetectionTool(BaseTool):
    description = "使用 20 日 BOLL 布林带检测收盘价上轨和下轨突破"
    parameters = [
        {
            "name": "ts_code",
            "type": "string",
            "description": "数据库内的股票代码或名称",
            "required": True,
        },
        {
            "name": "start_date",
            "type": "string",
            "description": "YYYY-MM-DD，可选",
            "required": False,
        },
        {
            "name": "end_date",
            "type": "string",
            "description": "YYYY-MM-DD，可选",
            "required": False,
        },
    ]

    def call(self, params: str, **kwargs) -> str:
        del kwargs
        try:
            args = json.loads(params)
            stock_code, stock_name = _resolve_stock(str(args["ts_code"]).strip())
            latest = execute_read_query(
                "SELECT MAX(trade_date) AS latest_date FROM stock_daily_price WHERE ts_code = ?",
                (stock_code,),
            ).iloc[0, 0]
            end_date = str(args.get("end_date") or latest)
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            start_date = str(
                args.get("start_date")
                or (end_dt - timedelta(days=BOLL_DEFAULT_DAYS)).strftime("%Y-%m-%d")
            )
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            if start_dt >= end_dt:
                return "检测范围起始日期必须早于结束日期"
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            return f"参数不正确：{exc}"

        fetch_start = (start_dt - timedelta(days=BOLL_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        frame = execute_read_query(
            "SELECT ts_code, stock_name, trade_date, close FROM stock_daily_price "
            "WHERE ts_code = ? AND trade_date >= ? AND trade_date <= ? ORDER BY trade_date",
            (stock_code, fetch_start, end_date),
        )
        if len(frame) < BOLL_WINDOW:
            return f"历史数据不足（仅 {len(frame)} 条），至少需要 {BOLL_WINDOW} 条"

        calculated = calculate_bollinger_bands(
            frame, window=BOLL_WINDOW, std_multiplier=BOLL_STD_MULTIPLIER
        )
        mask = calculated["trade_date"].between(start_date, end_date)
        overbought, oversold = detect_bollinger_breakouts(calculated.loc[mask])

        overbought_md = (
            overbought[["trade_date", "close", "boll_upper"]]
            .rename(columns={"trade_date": "上轨突破日期", "close": "收盘价", "boll_upper": "上轨"})
            .round(2)
            .to_markdown(index=False)
            if not overbought.empty
            else "检测范围内无上轨突破"
        )
        oversold_md = (
            oversold[["trade_date", "close", "boll_lower"]]
            .rename(columns={"trade_date": "下轨突破日期", "close": "收盘价", "boll_lower": "下轨"})
            .round(2)
            .to_markdown(index=False)
            if not oversold.empty
            else "检测范围内无下轨突破"
        )

        _prepare_runtime()
        settings = get_settings()
        image_path = allocate_image_path(
            settings.runtime_dir, f"boll_{stock_code.replace('.', '_')}"
        )
        plot_bollinger(
            calculated,
            overbought,
            oversold,
            stock_code=stock_code,
            stock_name=stock_name,
            window=BOLL_WINDOW,
            multiplier=BOLL_STD_MULTIPLIER,
            save_path=image_path,
        )
        return "\n\n".join(
            [
                f"## BOLL 布林带异常检测（{BOLL_WINDOW} 日，{BOLL_STD_MULTIPLIER:g} 倍标准差）",
                f"- **股票**：{stock_name}（{stock_code}）",
                f"- **检测范围**：{start_date} 至 {end_date}",
                f"### 上轨突破（{len(overbought)} 天）\n{overbought_md}",
                f"### 下轨突破（{len(oversold)} 天）\n{oversold_md}",
                _image_markdown(image_path, "BOLL 检测图"),
                "上下轨突破是简化的技术分析口径，不构成投资建议。",
            ]
        )
