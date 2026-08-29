"""Chart rendering and lifecycle management for runtime images."""

from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.sans-serif"] = [
    "SimHei",
    "Microsoft YaHei",
    "SimSun",
    "Arial Unicode MS",
]
plt.rcParams["axes.unicode_minus"] = False


def safe_label(value: object) -> str:
    return str(value).replace("%", "%%").replace("{", "{{").replace("}", "}}")


def allocate_image_path(runtime_dir: Path, prefix: str) -> Path:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir / f"{prefix}_{uuid4().hex}.png"


def markdown_image_path(path: Path, project_root: Path) -> str:
    try:
        relative = path.resolve().relative_to(project_root.resolve())
    except ValueError:
        return path.resolve().as_posix()
    return relative.as_posix()


def cleanup_runtime_images(
    runtime_dir: Path,
    *,
    retention_hours: int = 24,
    retention_count: int = 100,
) -> None:
    """Delete only generated PNGs in the dedicated runtime directory."""
    if not runtime_dir.is_dir():
        return
    images = sorted(
        (path for path in runtime_dir.glob("*.png") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    cutoff = time.time() - retention_hours * 3600
    for index, path in enumerate(images):
        if index >= retention_count or path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)


def _prepare_series(frame: pd.DataFrame) -> tuple[np.ndarray, list[str], list[str]]:
    x = np.arange(len(frame))
    labels = [safe_label(item) for item in frame.iloc[:, 0].tolist()]
    numeric = frame.select_dtypes(include="number").columns.tolist()
    if frame.columns[0] in numeric:
        numeric.remove(frame.columns[0])
    if not numeric:
        raise ValueError("查询结果没有可绘制的数值列")
    return x, labels, numeric


def plot_query_result(frame: pd.DataFrame, save_path: Path, *, bar_max_rows: int = 12) -> None:
    """Render a compact bar chart for small results and a line chart for trends."""
    x, labels, numeric = _prepare_series(frame)
    figure, axis = plt.subplots(figsize=(10, 6))
    if len(frame) <= bar_max_rows:
        width = 0.8 / max(1, len(numeric))
        for index, column in enumerate(numeric):
            offset = (index - (len(numeric) - 1) / 2) * width
            axis.bar(x + offset, frame[column].to_numpy(), width=width, label=safe_label(column))
    else:
        for column in numeric:
            axis.plot(
                x,
                frame[column].to_numpy(),
                linewidth=1.5,
                marker="o",
                markersize=3,
                label=safe_label(column),
            )

    step = max(1, int(np.ceil(len(labels) / 10)))
    selected = x[::step]
    axis.set_xticks(selected)
    axis.set_xticklabels([labels[index] for index in selected], rotation=45, ha="right")
    axis.set_title("查询结果可视化")
    axis.set_xlabel(safe_label(frame.columns[0]))
    axis.set_ylabel("数值")
    axis.legend()
    figure.tight_layout()
    figure.savefig(save_path, dpi=140)
    plt.close(figure)


def plot_forecast(
    history: pd.DataFrame,
    forecast_values: pd.Series,
    forecast_dates: list[str],
    *,
    stock_code: str,
    stock_name: str,
    save_path: Path,
) -> None:
    figure, axis = plt.subplots(figsize=(12, 6))
    history_x = np.arange(len(history))
    forecast_x = np.arange(len(history), len(history) + len(forecast_values))
    history_values = history["close"].astype(float).to_numpy()

    axis.plot(history_x, history_values, linewidth=1.2, label="历史收盘价")
    line_x = np.insert(forecast_x, 0, history_x[-1])
    line_y = np.insert(np.asarray(forecast_values, dtype=float), 0, history_values[-1])
    axis.plot(
        line_x,
        line_y,
        linewidth=1.8,
        linestyle="--",
        marker="o",
        markersize=4,
        color="#d62728",
        label="ARIMA 预测价",
    )

    labels = history["trade_date"].tolist() + forecast_dates
    positions = np.arange(len(labels))
    step = max(1, int(np.ceil(len(labels) / 10)))
    selected = positions[::step]
    axis.set_xticks(selected)
    axis.set_xticklabels([safe_label(labels[index]) for index in selected], rotation=45)
    axis.set_title(f"ARIMA 价格预测 - {stock_name}（{stock_code}）")
    axis.set_xlabel("日期")
    axis.set_ylabel("收盘价")
    axis.legend()
    figure.tight_layout()
    figure.savefig(save_path, dpi=140)
    plt.close(figure)


def plot_bollinger(
    frame: pd.DataFrame,
    overbought: pd.DataFrame,
    oversold: pd.DataFrame,
    *,
    stock_code: str,
    stock_name: str,
    window: int,
    multiplier: float,
    save_path: Path,
) -> None:
    figure, axis = plt.subplots(figsize=(12, 6))
    x = np.arange(len(frame))
    axis.plot(x, frame["close"].astype(float), linewidth=1.2, label="收盘价")
    axis.plot(x, frame["boll_mid"], linestyle="--", label=f"中轨（{window} 日均线）")
    axis.plot(x, frame["boll_upper"], linewidth=1.0, label=f"上轨（+{multiplier:g}σ）")
    axis.plot(x, frame["boll_lower"], linewidth=1.0, label=f"下轨（-{multiplier:g}σ）")

    if not overbought.empty:
        mask = frame["trade_date"].isin(overbought["trade_date"])
        axis.scatter(x[mask], frame.loc[mask, "close"], marker="^", color="red", label="上轨突破")
    if not oversold.empty:
        mask = frame["trade_date"].isin(oversold["trade_date"])
        axis.scatter(x[mask], frame.loc[mask, "close"], marker="v", color="green", label="下轨突破")

    labels = frame["trade_date"].tolist()
    step = max(1, int(np.ceil(len(labels) / 10)))
    selected = x[::step]
    axis.set_xticks(selected)
    axis.set_xticklabels([safe_label(labels[index]) for index in selected], rotation=45)
    axis.set_title(f"BOLL 异常检测 - {stock_name}（{stock_code}）")
    axis.set_xlabel("交易日期")
    axis.set_ylabel("收盘价")
    axis.legend()
    figure.tight_layout()
    figure.savefig(save_path, dpi=140)
    plt.close(figure)
