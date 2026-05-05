from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from trading_app.schemas import Bar, Signal


@dataclass(frozen=True)
class StrategyParams:
    short_window: int = 8
    long_window: int = 30
    min_crossover_pct: float = 0.002
    momentum_window: int = 30
    volatility_window: int = 20
    min_momentum_pct: float = 0.01
    max_volatility_pct: float = 0.045
    max_drawdown_from_peak_pct: float = 0.18
    min_buy_score: float = 0.75
    sell_score: float = -0.35
    max_positions: int = 5
    stop_loss_pct: float = 0.08
    trailing_stop_pct: float = 0.12


class Strategy(Protocol):
    name: str
    params: StrategyParams

    def generate_signal(self, symbol: str, bars: Sequence[Bar]) -> Signal:
        ...


class MovingAverageCrossoverStrategy:
    name = "risk_adjusted_momentum_rotation"

    def __init__(self, params: StrategyParams | None = None) -> None:
        self.params = params or StrategyParams()
        if self.params.short_window >= self.params.long_window:
            raise ValueError("short_window must be less than long_window")

    def generate_signal(self, symbol: str, bars: Sequence[Bar]) -> Signal:
        """Generate a risk-adjusted momentum signal for watchlist rotation.

        The older strategy bought too easily on a simple moving-average crossover.
        This version requires trend + momentum confirmation, penalizes unstable
        tickers, and emits SELL signals when drawdown/volatility protection matters.
        """

        if len(bars) < self.params.long_window:
            return Signal(
                symbol=symbol,
                action="HOLD",
                confidence=0.0,
                reason="not enough bars for long moving average",
            )

        closes = [float(bar.close) for bar in bars]
        short_average = sum(closes[-self.params.short_window :]) / self.params.short_window
        long_average = sum(closes[-self.params.long_window :]) / self.params.long_window
        crossover_pct = (short_average - long_average) / max(long_average, 1e-9)

        momentum_window = min(max(1, self.params.momentum_window), len(closes) - 1)
        recent_momentum = (closes[-1] / max(closes[-momentum_window - 1], 1e-9)) - 1

        volatility_window = min(max(2, self.params.volatility_window), len(closes) - 1)
        recent_returns = [
            (closes[index] / max(closes[index - 1], 1e-9)) - 1
            for index in range(len(closes) - volatility_window, len(closes))
        ]
        avg_return = sum(recent_returns) / len(recent_returns) if recent_returns else 0.0
        variance = sum((value - avg_return) ** 2 for value in recent_returns) / max(len(recent_returns) - 1, 1)
        volatility = variance**0.5

        recent_peak = max(closes[-self.params.long_window :])
        drawdown_from_peak = (closes[-1] / max(recent_peak, 1e-9)) - 1
        above_long_average = closes[-1] >= long_average

        trend_score = crossover_pct / max(self.params.min_crossover_pct, 1e-9)
        momentum_score = recent_momentum / max(abs(self.params.min_momentum_pct), 1e-9)
        volatility_penalty = max(0.0, volatility / max(self.params.max_volatility_pct, 1e-9) - 1.0)
        drawdown_penalty = max(0.0, abs(drawdown_from_peak) / max(self.params.max_drawdown_from_peak_pct, 1e-9) - 1.0)
        raw_score = (0.55 * trend_score) + (0.45 * momentum_score) - volatility_penalty - drawdown_penalty

        confidence = max(0.0, min(abs(raw_score) / 3.0, 1.0))
        risk_notes = (
            f"score={raw_score:.2f}, crossover={crossover_pct:.2%}, momentum={recent_momentum:.2%}, "
            f"volatility={volatility:.2%}, drawdown={drawdown_from_peak:.2%}"
        )

        if drawdown_from_peak <= -self.params.max_drawdown_from_peak_pct:
            return Signal(
                symbol=symbol,
                action="SELL",
                confidence=round(max(confidence, 0.65), 4),
                reason=f"risk-adjusted strategy: drawdown protection triggered; {risk_notes}",
            )

        if volatility > self.params.max_volatility_pct * 1.75 and recent_momentum < 0:
            return Signal(
                symbol=symbol,
                action="SELL",
                confidence=round(max(confidence, 0.55), 4),
                reason=f"risk-adjusted strategy: volatile negative momentum; {risk_notes}",
            )

        if raw_score >= self.params.min_buy_score and above_long_average and recent_momentum >= self.params.min_momentum_pct:
            return Signal(
                symbol=symbol,
                action="BUY",
                confidence=round(max(confidence, 0.5), 4),
                reason=f"risk-adjusted strategy: trend and momentum confirmed; {risk_notes}",
            )

        if raw_score <= self.params.sell_score or (crossover_pct < -self.params.min_crossover_pct and recent_momentum < 0):
            return Signal(
                symbol=symbol,
                action="SELL",
                confidence=round(max(confidence, 0.5), 4),
                reason=f"risk-adjusted strategy: trend/momentum deterioration; {risk_notes}",
            )

        return Signal(
            symbol=symbol,
            action="HOLD",
            confidence=round(min(confidence, 0.49), 4),
            reason=f"risk-adjusted strategy: no strong risk-adjusted edge; {risk_notes}",
        )
