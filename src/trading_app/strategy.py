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
    min_buy_score: float = 8.0
    sell_score: float = -0.35
    max_positions: int = 5
    stop_loss_pct: float = 0.08
    trailing_stop_pct: float = 0.12
    vwap_window: int = 20
    atr_period: int = 14
    atr_stop_multiplier: float = 1.5
    atr_trailing_multiplier: float = 2.0
    take_profit_r_multiple: float = 2.0
    min_relative_strength_pct: float = 0.0
    base_risk_fraction: float = 0.06
    min_risk_fraction: float = 0.01
    max_risk_fraction: float = 0.12
    account_equity: float = 10_000.0
    intraday_timeframe: str = "5Min"


class Strategy(Protocol):
    name: str
    params: StrategyParams

    def generate_signal(self, symbol: str, bars: Sequence[Bar]) -> Signal:
        ...


class MovingAverageCrossoverStrategy:
    name = "intraday_vwap_relative_strength_adaptive_risk"

    def __init__(self, params: StrategyParams | None = None) -> None:
        self.params = params or StrategyParams()
        if self.params.short_window >= self.params.long_window:
            raise ValueError("short_window must be less than long_window")
        if self.params.min_risk_fraction > self.params.max_risk_fraction:
            raise ValueError("min_risk_fraction must be <= max_risk_fraction")

    @property
    def _timeframe_label(self) -> str:
        return f"intraday_{self.params.intraday_timeframe.lower()}"

    def _risk_sizing(self, confidence: float, volatility: float, drawdown_from_peak: float) -> tuple[float, float]:
        """Adaptive long-only cash sizing: higher conviction + calmer tape = larger, no leverage."""
        volatility_ratio = volatility / max(self.params.max_volatility_pct, 1e-9)
        volatility_scale = max(0.20, min(1.25, 1.0 / max(volatility_ratio, 0.50)))
        drawdown_scale = max(0.25, 1.0 + min(drawdown_from_peak, 0.0))
        confidence_scale = max(0.30, min(1.20, confidence))
        raw_fraction = self.params.base_risk_fraction * volatility_scale * drawdown_scale * confidence_scale
        risk_fraction = max(self.params.min_risk_fraction, min(self.params.max_risk_fraction, raw_fraction))
        target_notional = max(0.0, self.params.account_equity * risk_fraction)
        return round(risk_fraction, 6), round(target_notional, 4)

    def _exit_signal(self, symbol: str, confidence: float, reason: str) -> Signal:
        return Signal(
            symbol=symbol,
            action="SELL",
            confidence=round(max(confidence, 0.5), 4),
            reason=f"intraday VWAP/relative strength strategy: long exit only, never short; {reason}",
            strategy_mode=self.name,
            timeframe=self._timeframe_label,
            risk_fraction=0.0,
            target_notional=0.0,
        )

    def generate_signal(self, symbol: str, bars: Sequence[Bar]) -> Signal:
        """Generate an intraday long-only signal with adaptive risk sizing.

        The engine only opens long cash positions, never shorts and never uses
        margin. SELL means "close/reduce an existing long", not "open short".
        Risk fraction is automatically reduced when volatility/drawdown rises and
        increased only when trend, momentum, and price stability confirm each other.
        """

        if len(bars) < self.params.long_window:
            return Signal(
                symbol=symbol,
                action="HOLD",
                confidence=0.0,
                reason="intraday long-only strategy: not enough 5-minute bars for long moving average",
                strategy_mode=self.name,
                timeframe=self._timeframe_label,
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

        vwap_window = min(max(2, self.params.vwap_window), len(bars))
        vwap_bars = list(bars)[-vwap_window:]
        total_volume = sum(max(float(bar.volume), 0.0) for bar in vwap_bars)
        if total_volume > 0:
            vwap = sum(float(bar.close) * max(float(bar.volume), 0.0) for bar in vwap_bars) / total_volume
        else:
            vwap = sum(float(bar.close) for bar in vwap_bars) / len(vwap_bars)
        above_vwap = closes[-1] >= vwap

        atr_period = min(max(2, self.params.atr_period), len(bars) - 1)
        atr_ranges = []
        for index in range(len(bars) - atr_period, len(bars)):
            current = bars[index]
            previous_close = float(bars[index - 1].close) if index > 0 else float(current.close)
            atr_ranges.append(
                max(
                    float(current.high) - float(current.low),
                    abs(float(current.high) - previous_close),
                    abs(float(current.low) - previous_close),
                )
            )
        atr = sum(atr_ranges) / len(atr_ranges) if atr_ranges else 0.0
        atr_pct = atr / max(closes[-1], 1e-9)

        recent_relative_strength = recent_momentum - avg_return

        trend_score = crossover_pct / max(self.params.min_crossover_pct, 1e-9)
        momentum_score = recent_momentum / max(abs(self.params.min_momentum_pct), 1e-9)
        volatility_penalty = max(0.0, volatility / max(self.params.max_volatility_pct, 1e-9) - 1.0)
        drawdown_penalty = max(0.0, abs(drawdown_from_peak) / max(self.params.max_drawdown_from_peak_pct, 1e-9) - 1.0)
        vwap_penalty = 0.75 if not above_vwap else 0.0
        relative_strength_score = recent_relative_strength / max(abs(self.params.min_momentum_pct), 1e-9)
        raw_score = (0.40 * trend_score) + (0.35 * momentum_score) + (0.25 * relative_strength_score) - volatility_penalty - drawdown_penalty - vwap_penalty

        confidence_scale_denominator = max(10.0, abs(self.params.min_buy_score), abs(self.params.sell_score), 1e-9)
        confidence = max(0.0, min(abs(raw_score) / (abs(raw_score) + confidence_scale_denominator), 1.0))
        risk_notes = (
            f"score={raw_score:.2f}, crossover={crossover_pct:.2%}, momentum={recent_momentum:.2%}, "
            f"relative strength={recent_relative_strength:.2%}, VWAP={vwap:.2f}, ATR={atr:.2f} ({atr_pct:.2%}), "
            f"volatility={volatility:.2%}, drawdown={drawdown_from_peak:.2%}"
        )

        if drawdown_from_peak <= -self.params.max_drawdown_from_peak_pct:
            return self._exit_signal(
                symbol,
                max(confidence, 0.65),
                f"drawdown protection triggered; {risk_notes}",
            )

        if volatility > self.params.max_volatility_pct * 1.75 and recent_momentum < 0:
            return self._exit_signal(
                symbol,
                max(confidence, 0.55),
                f"volatile negative momentum; {risk_notes}",
            )

        if (
            raw_score >= self.params.min_buy_score
            and above_long_average
            and above_vwap
            and recent_momentum >= self.params.min_momentum_pct
            and recent_relative_strength >= self.params.min_relative_strength_pct
        ):
            buy_confidence = max(confidence, 0.5)
            risk_fraction, target_notional = self._risk_sizing(buy_confidence, volatility + atr_pct, drawdown_from_peak)
            return Signal(
                symbol=symbol,
                action="BUY",
                confidence=round(buy_confidence, 4),
                reason=(
                    "intraday VWAP/relative strength strategy: trend, VWAP, ATR risk and relative strength confirmed; "
                    f"adaptive cash risk={risk_fraction:.2%}, target=${target_notional:.2f}, no leverage; {risk_notes}"
                ),
                strategy_mode=self.name,
                timeframe=self._timeframe_label,
                risk_fraction=risk_fraction,
                target_notional=target_notional,
            )

        if raw_score <= self.params.sell_score or (crossover_pct < -self.params.min_crossover_pct and recent_momentum < 0):
            return self._exit_signal(
                symbol,
                max(confidence, 0.5),
                f"trend/momentum deterioration; {risk_notes}",
            )

        filter_note = "price below VWAP filter; " if not above_vwap else ""
        return Signal(
            symbol=symbol,
            action="HOLD",
            confidence=round(min(confidence, 0.49), 4),
            reason=f"intraday VWAP/relative strength strategy: {filter_note}no strong risk-adjusted long edge; {risk_notes}",
            strategy_mode=self.name,
            timeframe=self._timeframe_label,
            risk_fraction=0.0,
            target_notional=0.0,
        )
