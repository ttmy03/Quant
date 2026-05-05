from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from trading_app.schemas import Bar, Signal


@dataclass(frozen=True)
class StrategyParams:
    short_window: int = 5
    long_window: int = 20
    min_crossover_pct: float = 0.001


class Strategy(Protocol):
    name: str
    params: StrategyParams

    def generate_signal(self, symbol: str, bars: Sequence[Bar]) -> Signal:
        ...


class MovingAverageCrossoverStrategy:
    name = "moving_average_crossover"

    def __init__(self, params: StrategyParams | None = None) -> None:
        self.params = params or StrategyParams()
        if self.params.short_window >= self.params.long_window:
            raise ValueError("short_window must be less than long_window")

    def generate_signal(self, symbol: str, bars: Sequence[Bar]) -> Signal:
        if len(bars) < self.params.long_window:
            return Signal(
                symbol=symbol,
                action="HOLD",
                confidence=0.0,
                reason="not enough bars for long moving average",
            )

        closes = [bar.close for bar in bars]
        short_average = sum(closes[-self.params.short_window :]) / self.params.short_window
        long_average = sum(closes[-self.params.long_window :]) / self.params.long_window
        crossover_pct = (short_average - long_average) / long_average
        confidence = min(abs(crossover_pct) / max(self.params.min_crossover_pct, 1e-9), 1.0)

        if crossover_pct > self.params.min_crossover_pct:
            action = "BUY"
            reason = "short moving average is above long moving average"
        elif crossover_pct < -self.params.min_crossover_pct:
            action = "SELL"
            reason = "short moving average is below long moving average"
        else:
            action = "HOLD"
            confidence = 0.0
            reason = "moving averages are within the neutral band"

        return Signal(symbol=symbol, action=action, confidence=confidence, reason=reason)
