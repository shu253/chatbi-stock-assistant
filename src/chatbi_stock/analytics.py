"""Pure analytical functions that are independent from the agent framework."""

from __future__ import annotations

import pandas as pd


def calculate_bollinger_bands(
    frame: pd.DataFrame,
    *,
    window: int = 20,
    std_multiplier: float = 2.0,
) -> pd.DataFrame:
    """Return a copy with BOLL middle, upper and lower bands."""
    if window < 2:
        raise ValueError("window 必须至少为 2")
    if "close" not in frame.columns:
        raise ValueError("输入数据必须包含 close 列")

    result = frame.copy().reset_index(drop=True)
    close = pd.to_numeric(result["close"], errors="raise")
    middle = close.rolling(window=window).mean()
    deviation = close.rolling(window=window).std()
    result["boll_mid"] = middle
    result["boll_upper"] = middle + std_multiplier * deviation
    result["boll_lower"] = middle - std_multiplier * deviation
    return result


def detect_bollinger_breakouts(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split valid BOLL rows into upper- and lower-band breakouts."""
    required = {"close", "boll_upper", "boll_lower"}
    if not required.issubset(frame.columns):
        raise ValueError(f"输入数据缺少字段：{sorted(required - set(frame.columns))}")
    valid = frame.dropna(subset=["boll_upper", "boll_lower"])
    return (
        valid[valid["close"] > valid["boll_upper"]].copy(),
        valid[valid["close"] < valid["boll_lower"]].copy(),
    )
