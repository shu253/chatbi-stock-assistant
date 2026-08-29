from __future__ import annotations

import pandas as pd

from chatbi_stock.analytics import calculate_bollinger_bands, detect_bollinger_breakouts


def test_bollinger_bands_and_breakouts() -> None:
    frame = pd.DataFrame(
        {
            "trade_date": pd.date_range("2025-01-01", periods=8).strftime("%Y-%m-%d"),
            "close": [10.0, 10.0, 10.0, 10.0, 30.0, 10.0, 10.0, 1.0],
        }
    )
    result = calculate_bollinger_bands(frame, window=3, std_multiplier=1.0)
    upper, lower = detect_bollinger_breakouts(result)
    assert "boll_mid" in result.columns
    assert not upper.empty
    assert not lower.empty


def test_bollinger_does_not_mutate_input() -> None:
    frame = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
    calculate_bollinger_bands(frame, window=2)
    assert list(frame.columns) == ["close"]
