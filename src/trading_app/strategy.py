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
    name = "adaptive_momentum_crossover"

    def __init__(self, params: StrategyParams | None = None) -> None:
        self.params = params or StrategyParams()
        if self.params.short_window >= self.params.long_window:
            raise ValueError("short_window must be less than long_window")

    def generate_signal(self, symbol: str, bars: Sequence[Bar]) -> Signal:
        """Generate a risk-aware multi-symbol signal.

        The strategy still uses the proven moving-average crossover base, but it now also
        checks recent momentum, volatility and drawdown so several watchlist symbols can
        independently become BUY/SELL candidates in one scheduler run.
        """

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
        crossover_pct = (short_average - long_average) / max(long_average, 1e-9)

        momentum_window = min(20, len(closes) - 1)
        recent_momentum = (closes[-1] / max(closes[-momentum_window - 1], 1e-9)) - 1 if momentum_window else 0.0
        recent_returns = [
            (closes[index] / max(closes[index - 1], 1e-9)) - 1
            for index in range(max(1, len(closes) - momentum_window), len(closes))
        ]
        avg_return = sum(recent_returns) / len(recent_returns) if recent_returns else 0.0
        variance = sum((value - avg_return) ** 2 for value in recent_returns) / max(len(recent_returns) - 1, 1)
        volatility = variance ** 0.5
        recent_peak = max(closes[-self.params.long_window :])
        drawdown_from_peak = (closes[-1] / max(recent_peak, 1e-9)) - 1

        trend_score = crossover_pct / max(self.params.min_crossover_pct, 1e-9)
        momentum_score = recent_momentum / 0.03
        risk_penalty = min(volatility / 0.04, 1.0) + max(0.0, -drawdown_from_peak - 0.12)
        raw_score = (0.65 * trend_score) + (0.35 * momentum_score) - risk_penalty
        confidence = max(0.0, min(abs(raw_score) / 2.0, 1.0))

        if raw_score > 0.55 and crossover_pct > self.params.min_crossover_pct and recent_momentum > 0:
            action = "BUY"
            reason = (
                "adaptive strategy: uptrend confirmed by moving averages and positive 20-day momentum; "
                f"score={raw_score:.2f}, momentum={recent_momentum:.2%}, drawdown={drawdown_from_peak:.2%}"
            )
        elif raw_score < -0.55 or (crossover_pct < -self.params.min_crossover_pct and recent_momentum < 0):
            action = "SELL"
            reason = (
                "adaptive strategy: downtrend or momentum deterioration detected; "
                f"score={raw_score:.2f}, momentum={recent_momentum:.2%}, drawdown={drawdown_from_peak:.2%}"
            )
        else:
            action = "HOLD"
            confidence = min(confidence, 0.49)
            reason = (
                "adaptive strategy: no strong risk-adjusted edge; "
                f"score={raw_score:.2f}, momentum={recent_momentum:.2%}, drawdown={drawdown_from_peak:.2%}"
            )

        return Signal(symbol=symbol, action=action, confidence=round(confidence, 4), reason=reason)
