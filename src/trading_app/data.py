from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

from trading_app.schemas import Bar


def generate_synthetic_bars(
    symbol: str = "AAPL",
    days: int = 180,
    seed: int = 42,
    start_price: float = 100.0,
    drift: float = 0.0005,
    volatility: float = 0.012,
) -> list[Bar]:
    """Generate deterministic OHLCV bars for tests, demos, and unconfigured mode."""

    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, volatility, size=days)
    prices = start_price * np.cumprod(1 + np.clip(returns, -0.2, 0.2))
    start_date = datetime.now(UTC).date() - timedelta(days=days)
    bars: list[Bar] = []

    previous_close = start_price
    for index, close in enumerate(prices):
        timestamp = datetime.combine(start_date + timedelta(days=index), datetime.min.time(), tzinfo=UTC)
        open_price = previous_close
        high = max(open_price, float(close)) * (1 + abs(float(rng.normal(0.001, 0.002))))
        low = min(open_price, float(close)) * (1 - abs(float(rng.normal(0.001, 0.002))))
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=timestamp,
                open=round(open_price, 4),
                high=round(high, 4),
                low=round(low, 4),
                close=round(float(close), 4),
                volume=float(rng.integers(100_000, 2_000_000)),
            )
        )
        previous_close = float(close)

    return bars


def returns_from_bars(bars: list[Bar]) -> list[float]:
    if len(bars) < 2:
        return []
    returns: list[float] = []
    for previous, current in zip(bars, bars[1:]):
        returns.append((current.close / previous.close) - 1)
    return returns
