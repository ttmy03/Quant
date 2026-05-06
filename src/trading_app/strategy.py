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
    adam_eve_enabled: bool = True
    adam_eve_rsi_reversal: float = 36.0
    adam_eve_rsi_pullback: float = 58.0
    adam_eve_volume_mult: float = 0.75
    adam_eve_atr_min_pct: float = 0.001
    adam_eve_atr_max_pct: float = 0.080
    adam_eve_ema200_floor: float = 0.92
    adam_eve_bb_reclaim: float = 0.995
    adam_eve_min_drawdown_pct: float = 0.035
    adam_eve_pullback_symbols: tuple[str, ...] = ()


def _ema(values: Sequence[float], period: int) -> float:
    if not values:
        return 0.0
    period = max(1, min(period, len(values)))
    multiplier = 2 / (period + 1)
    ema = float(values[0])
    for value in values[1:]:
        ema = (float(value) * multiplier) + (ema * (1 - multiplier))
    return ema


def _rsi(values: Sequence[float], period: int) -> float:
    if len(values) < 2:
        return 50.0
    deltas = [float(values[index]) - float(values[index - 1]) for index in range(1, len(values))]
    window = deltas[-max(1, min(period, len(deltas))) :]
    gains = [delta for delta in window if delta > 0]
    losses = [-delta for delta in window if delta < 0]
    avg_gain = sum(gains) / len(window) if window else 0.0
    avg_loss = sum(losses) / len(window) if window else 0.0
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _bollinger_bands(values: Sequence[float], period: int) -> tuple[float, float, float]:
    window = [float(value) for value in values[-max(2, min(period, len(values))) :]]
    middle = sum(window) / len(window) if window else 0.0
    variance = sum((value - middle) ** 2 for value in window) / max(len(window), 1)
    std = variance**0.5
    return middle + (2 * std), middle, middle - (2 * std)


def _macd_hist(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    macd_line = _ema(values, 12) - _ema(values, 26)
    # Approximate the signal line from the latest MACD slope to avoid carrying state.
    previous_macd_line = _ema(values[:-1], 12) - _ema(values[:-1], 26) if len(values) > 2 else macd_line
    signal_line = (macd_line * (2 / 10)) + (previous_macd_line * (1 - (2 / 10)))
    return macd_line - signal_line


class Strategy(Protocol):
    name: str
    params: StrategyParams

    def generate_signal(self, symbol: str, bars: Sequence[Bar]) -> Signal:
        ...


class MovingAverageCrossoverStrategy:
    name = "stock_watchlist_adam_eve_vwap_adaptive_risk"

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
            reason=f"stock watchlist Adam/Eve + VWAP strategy: long exit only, never short; {reason}",
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

        lows = [float(bar.low) for bar in bars]
        highs = [float(bar.high) for bar in bars]
        opens = [float(bar.open) for bar in bars]
        volumes = [max(float(bar.volume), 0.0) for bar in bars]
        current_open = opens[-1]
        current_high = highs[-1]
        current_low = lows[-1]
        current_close = closes[-1]
        candle_range = max(current_high - current_low, 1e-9)
        candle_bottom = min(current_open, current_close)
        candle_top = max(current_open, current_close)
        lower_wick_ratio = max(0.0, (candle_bottom - current_low) / candle_range)
        upper_wick_ratio = max(0.0, (current_high - candle_top) / candle_range)
        bullish_close = current_close > current_open
        volume_window = min(30, len(volumes))
        volume_mean = sum(volumes[-volume_window:]) / max(volume_window, 1)

        ema21 = _ema(closes, 21)
        ema55 = _ema(closes, 55)
        ema200 = _ema(closes, min(200, len(closes)))
        rsi14 = _rsi(closes, 14)
        rsi_fast = _rsi(closes, 4)
        previous_rsi_fast = _rsi(closes[:-1], 4) if len(closes) > 5 else rsi_fast
        macd_hist = _macd_hist(closes)
        previous_macd_hist = _macd_hist(closes[:-1]) if len(closes) > 35 else macd_hist
        bb_upper, bb_middle, bb_lower = _bollinger_bands(closes, 20)
        bb_width = (bb_upper - bb_lower) / max(bb_middle, 1e-9)
        low_48_previous = min(lows[-49:-1]) if len(lows) >= 49 else min(lows[:-1] or lows)
        high_48_previous = max(highs[-49:-1]) if len(highs) >= 49 else max(highs[:-1] or highs)
        low_48 = min(lows[-48:])
        high_48 = max(highs[-48:])
        range_position = (current_close - low_48) / max(high_48 - low_48, 1e-9)
        drawdown_12h = (current_close / max(high_48_previous, 1e-9)) - 1
        market_drop_3h = (current_close / max(closes[-13], 1e-9) - 1) if len(closes) >= 13 else recent_momentum
        market_pump_1h = (current_close / max(closes[-5], 1e-9) - 1) if len(closes) >= 5 else recent_momentum

        adam_eve_base_filter = (
            self.params.adam_eve_enabled
            and volume_mean > 0
            and volumes[-1] > volume_mean * self.params.adam_eve_volume_mult
            and atr_pct > self.params.adam_eve_atr_min_pct
            and atr_pct < self.params.adam_eve_atr_max_pct
            and market_drop_3h > -0.080
            and market_pump_1h < 0.055
            and bb_width > 0.010
            and ema200 > 0
        )
        adam_flush = (
            current_low <= low_48_previous * 1.002
            and drawdown_12h < -self.params.adam_eve_min_drawdown_pct
            and lower_wick_ratio > 0.42
            and bullish_close
            and range_position < 0.46
            and current_close > current_low + atr * 0.35
        )
        eve_recovery = (
            current_close > bb_lower * self.params.adam_eve_bb_reclaim
            and rsi14 < self.params.adam_eve_rsi_reversal
            and rsi_fast >= previous_rsi_fast
            and current_close > closes[-2] * 0.990
            and current_close > ema200 * self.params.adam_eve_ema200_floor
        )
        allowed_pullback_symbols = {value.upper() for value in self.params.adam_eve_pullback_symbols}
        quality_pullback = (
            adam_eve_base_filter
            and (not allowed_pullback_symbols or symbol.upper() in allowed_pullback_symbols)
            and current_close > ema200 * 0.990
            and ema21 > ema55 * 1.001
            and current_low <= ema21 * 1.004
            and current_close > ema21 * 0.990
            and current_close > bb_middle * 0.985
            and 42 < rsi14 < self.params.adam_eve_rsi_pullback
            and rsi_fast >= previous_rsi_fast
            and macd_hist >= previous_macd_hist
            and lower_wick_ratio > 0.15
            and 0.20 < range_position < 0.75
            and market_drop_3h > -0.035
        )
        adam_eve_reversal = adam_eve_base_filter and adam_flush and eve_recovery

        if adam_eve_reversal or quality_pullback:
            setup = "adam_eve_reversal" if adam_eve_reversal else "quality_pullback"
            setup_score = 0.0
            if adam_eve_reversal:
                setup_score += 0.55 + min(0.20, lower_wick_ratio * 0.20) + min(0.15, abs(drawdown_12h))
            if quality_pullback:
                setup_score += 0.45 + min(0.20, max(recent_momentum, 0.0) * 5) + min(0.15, max(macd_hist - previous_macd_hist, 0.0))
            buy_confidence = max(confidence, min(0.92, setup_score))
            risk_fraction, target_notional = self._risk_sizing(buy_confidence, volatility + atr_pct, drawdown_from_peak)
            return Signal(
                symbol=symbol,
                action="BUY",
                confidence=round(buy_confidence, 4),
                reason=(
                    f"stock watchlist Adam/Eve setup={setup}: volume/ATR regime, Bollinger reclaim, RSI recovery and wick quality confirmed; "
                    f"adaptive cash risk={risk_fraction:.2%}, target=${target_notional:.2f}, no leverage; "
                    f"rsi={rsi14:.1f}, lower_wick={lower_wick_ratio:.0%}, range_position={range_position:.0%}, bb_width={bb_width:.2%}; {risk_notes}"
                ),
                strategy_mode=self.name,
                timeframe=self._timeframe_label,
                risk_fraction=risk_fraction,
                target_notional=target_notional,
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
                    "stock watchlist fallback: trend, VWAP, ATR risk and relative strength confirmed; "
                    f"adaptive cash risk={risk_fraction:.2%}, target=${target_notional:.2f}, no leverage; {risk_notes}"
                ),
                strategy_mode=self.name,
                timeframe=self._timeframe_label,
                risk_fraction=risk_fraction,
                target_notional=target_notional,
            )

        if raw_score <= self.params.sell_score or upper_wick_ratio > 0.55 or (crossover_pct < -self.params.min_crossover_pct and recent_momentum < 0):
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
            reason=f"stock watchlist Adam/Eve + VWAP strategy: {filter_note}no strong risk-adjusted long edge; {risk_notes}",
            strategy_mode=self.name,
            timeframe=self._timeframe_label,
            risk_fraction=0.0,
            target_notional=0.0,
        )
