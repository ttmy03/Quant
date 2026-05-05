from __future__ import annotations

from collections.abc import Sequence
from collections import defaultdict

from trading_app.monte_carlo import calculate_max_drawdown
from trading_app.schemas import (
    BacktestEquityPoint,
    BacktestMetrics,
    BacktestResult,
    BacktestTrade,
    Bar,
    Signal,
    StrategyParamsModel,
)
from trading_app.strategy import MovingAverageCrossoverStrategy, StrategyParams


def _average_true_range(bars: Sequence[Bar], period: int) -> float:
    """Return ATR using only bars that are known before the current decision bar."""
    if len(bars) < 2:
        return 0.0
    window = list(bars)[-max(2, period) :]
    ranges: list[float] = []
    for index in range(1, len(window)):
        current = window[index]
        previous_close = float(window[index - 1].close)
        ranges.append(
            max(
                float(current.high) - float(current.low),
                abs(float(current.high) - previous_close),
                abs(float(current.low) - previous_close),
            )
        )
    return sum(ranges) / len(ranges) if ranges else 0.0


def _long_exit_levels(entry: float, peak: float, prior_bars: Sequence[Bar], params: StrategyParams) -> tuple[float, float, float]:
    """Compute fixed/ATR hybrid stop, trailing stop, and take-profit levels for a long."""
    entry = max(float(entry), 1e-9)
    peak = max(float(peak), entry)
    atr = _average_true_range(prior_bars, params.atr_period)
    fixed_stop_distance = entry * params.stop_loss_pct
    fixed_trailing_distance = peak * params.trailing_stop_pct
    if atr > 0:
        stop_distance = min(fixed_stop_distance, atr * params.atr_stop_multiplier)
        trailing_distance = min(fixed_trailing_distance, atr * params.atr_trailing_multiplier)
    else:
        stop_distance = fixed_stop_distance
        trailing_distance = fixed_trailing_distance
    stop_price = entry - max(stop_distance, entry * 0.0025)
    trailing_stop_price = peak - max(trailing_distance, peak * 0.0025)
    take_profit_price = entry + max(stop_distance, entry * 0.0025) * params.take_profit_r_multiple
    return stop_price, trailing_stop_price, take_profit_price


def _trade_quality_metrics(trades: Sequence[BacktestTrade]) -> dict[str, object]:
    open_notional: dict[str, float] = {}
    winners: list[float] = []
    losers: list[float] = []
    per_symbol_pnl: dict[str, float] = defaultdict(float)
    per_symbol_trades: dict[str, int] = defaultdict(int)
    for trade in trades:
        symbol = trade.symbol.upper()
        if trade.side == "buy":
            open_notional[symbol] = float(trade.notional)
            per_symbol_trades[symbol] += 1
        elif trade.side == "sell" and symbol in open_notional:
            pnl = float(trade.notional) - open_notional.pop(symbol)
            per_symbol_pnl[symbol] += pnl
            per_symbol_trades[symbol] += 1
            if pnl > 0:
                winners.append(pnl)
            else:
                losers.append(abs(pnl))
    gross_profit = sum(winners)
    gross_loss = sum(losers)
    return {
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0 else (round(gross_profit, 6) if gross_profit > 0 else None),
        "avg_winner": round(gross_profit / len(winners), 4) if winners else None,
        "avg_loser": round(-(gross_loss / len(losers)), 4) if losers else None,
        "per_symbol_pnl": {symbol: round(value, 4) for symbol, value in sorted(per_symbol_pnl.items())},
        "per_symbol_trades": dict(sorted(per_symbol_trades.items())),
    }


def run_backtest(
    bars: Sequence[Bar],
    params: StrategyParams,
    *,
    initial_cash: float = 10_000.0,
    trade_notional: float = 1_000.0,
) -> BacktestResult:
    """Run a deterministic long-only moving-average crossover backtest."""

    strategy = MovingAverageCrossoverStrategy(StrategyParams(**{**params.__dict__, "account_equity": float(initial_cash)}))
    ordered_bars = sorted(bars, key=lambda bar: bar.timestamp)
    symbol = ordered_bars[-1].symbol if ordered_bars else "UNKNOWN"
    cash = float(initial_cash)
    position_qty = 0.0
    entry_notional = 0.0
    winning_round_trips = 0
    closed_round_trips = 0
    trades: list[BacktestTrade] = []
    equity_curve: list[BacktestEquityPoint] = []
    last_signal = Signal(
        symbol=symbol,
        action="HOLD",
        confidence=0.0,
        reason="no bars available",
    )

    for index, bar in enumerate(ordered_bars):
        last_signal = strategy.generate_signal(bar.symbol, ordered_bars[: index + 1])
        price = float(bar.close)

        if price > 0 and last_signal.action == "BUY" and position_qty <= 0 and cash > 0:
            notional = min(last_signal.target_notional if last_signal.target_notional > 0 else float(trade_notional), cash)
            qty = notional / price
            cash -= notional
            position_qty = qty
            entry_notional = notional
            trades.append(
                BacktestTrade(
                    timestamp=bar.timestamp,
                    symbol=bar.symbol,
                    side="buy",
                    qty=round(qty, 8),
                    price=round(price, 4),
                    notional=round(notional, 4),
                    reason=last_signal.reason,
                )
            )
        elif price > 0 and last_signal.action == "SELL" and position_qty > 0:
            qty = position_qty
            notional = qty * price
            cash += notional
            position_qty = 0.0
            closed_round_trips += 1
            if notional > entry_notional:
                winning_round_trips += 1
            entry_notional = 0.0
            trades.append(
                BacktestTrade(
                    timestamp=bar.timestamp,
                    symbol=bar.symbol,
                    side="sell",
                    qty=round(qty, 8),
                    price=round(price, 4),
                    notional=round(notional, 4),
                    reason=last_signal.reason,
                )
            )

        equity = cash + (position_qty * max(price, 0.0))
        equity_curve.append(
            BacktestEquityPoint(
                timestamp=bar.timestamp,
                equity=round(equity, 4),
                cash=round(cash, 4),
                position_qty=round(position_qty, 8),
                close=round(price, 4),
            )
        )

    final_equity = equity_curve[-1].equity if equity_curve else round(float(initial_cash), 4)
    exposure_pct = (
        sum(1 for point in equity_curve if point.position_qty > 0) / len(equity_curve)
        if equity_curve
        else 0.0
    )
    buy_and_hold_return = (
        (ordered_bars[-1].close / ordered_bars[0].close) - 1
        if len(ordered_bars) >= 2 and ordered_bars[0].close > 0
        else 0.0
    )
    win_rate = (winning_round_trips / closed_round_trips) if closed_round_trips else None
    diagnostics = _trade_quality_metrics(trades)

    metrics = BacktestMetrics(
        total_return=round((final_equity / float(initial_cash)) - 1, 6),
        final_equity=round(final_equity, 4),
        max_drawdown=round(calculate_max_drawdown([point.equity for point in equity_curve]), 6),
        trades_count=len(trades),
        win_rate=round(win_rate, 6) if win_rate is not None else None,
        exposure_pct=round(exposure_pct, 6),
        buy_and_hold_return=round(float(buy_and_hold_return), 6),
        **diagnostics,
    )

    return BacktestResult(
        symbol=symbol,
        strategy_name=MovingAverageCrossoverStrategy.name,
        params=StrategyParamsModel(**params.__dict__),
        initial_cash=float(initial_cash),
        trade_notional=float(trade_notional),
        last_signal=last_signal,
        trades=trades,
        equity_curve=equity_curve,
        metrics=metrics,
    )



def run_portfolio_backtest(
    bars_by_symbol: dict[str, Sequence[Bar]],
    params: StrategyParams,
    *,
    initial_cash: float = 10_000.0,
    trade_notional: float = 1_000.0,
) -> BacktestResult:
    """Run a multi-symbol portfolio backtest that mirrors the scheduler/live loop.

    The portfolio version now uses risk-aware execution on top of strategy signals:
    SELL/risk-exit decisions are processed first, BUY candidates are ranked by
    confidence, and max_positions prevents the engine from buying every weak
    crossover just because cash is available.
    """

    strategy = MovingAverageCrossoverStrategy(StrategyParams(**{**params.__dict__, "account_equity": float(initial_cash)}))
    ordered: dict[str, list[Bar]] = {
        symbol.upper(): sorted(list(bars), key=lambda bar: bar.timestamp)
        for symbol, bars in bars_by_symbol.items()
        if bars
    }
    if not ordered:
        return run_backtest([], params, initial_cash=initial_cash, trade_notional=trade_notional)

    bars_by_timestamp: dict[object, dict[str, Bar]] = defaultdict(dict)
    history_by_symbol: dict[str, list[Bar]] = {symbol: [] for symbol in ordered}
    latest_price: dict[str, float] = {}
    for symbol, bars in ordered.items():
        for bar in bars:
            bars_by_timestamp[bar.timestamp][symbol] = bar

    cash = float(initial_cash)
    positions: dict[str, float] = {symbol: 0.0 for symbol in ordered}
    entry_notional: dict[str, float] = {symbol: 0.0 for symbol in ordered}
    entry_price: dict[str, float] = {symbol: 0.0 for symbol in ordered}
    peak_price_since_entry: dict[str, float] = {symbol: 0.0 for symbol in ordered}
    winning_round_trips = 0
    closed_round_trips = 0
    trades: list[BacktestTrade] = []
    equity_curve: list[BacktestEquityPoint] = []
    last_signal = Signal(symbol="WATCHLIST_PORTFOLIO", action="HOLD", confidence=0.0, reason="portfolio backtest initialized")

    def close_position(symbol: str, bar: Bar, reason: str, *, execution_price: float | None = None) -> None:
        nonlocal cash, winning_round_trips, closed_round_trips
        qty = positions.get(symbol, 0.0)
        price = float(execution_price if execution_price is not None else bar.close)
        if qty <= 0 or price <= 0:
            return
        notional = qty * price
        cash += notional
        positions[symbol] = 0.0
        closed_round_trips += 1
        if notional > entry_notional.get(symbol, 0.0):
            winning_round_trips += 1
        entry_notional[symbol] = 0.0
        entry_price[symbol] = 0.0
        peak_price_since_entry[symbol] = 0.0
        trades.append(
            BacktestTrade(
                timestamp=bar.timestamp,
                symbol=symbol,
                side="sell",
                qty=round(qty, 8),
                price=round(price, 4),
                notional=round(notional, 4),
                reason=reason,
            )
        )

    for timestamp in sorted(bars_by_timestamp):
        day_bars = bars_by_timestamp[timestamp]
        for symbol in sorted(ordered):
            bar = day_bars.get(symbol)
            if bar is not None:
                history_by_symbol[symbol].append(bar)
                latest_price[symbol] = float(bar.close)
                if positions.get(symbol, 0.0) > 0:
                    peak_price_since_entry[symbol] = max(peak_price_since_entry.get(symbol, 0.0), float(bar.close))

        buy_candidates: list[tuple[float, str, Bar, Signal]] = []

        for symbol in sorted(ordered):
            history = history_by_symbol[symbol]
            if not history:
                continue
            bar = history[-1]
            price = float(bar.close)
            if price <= 0:
                continue

            signal = strategy.generate_signal(symbol, history)
            last_signal = signal
            held_qty = positions.get(symbol, 0.0)

            if held_qty > 0:
                entry = max(entry_price.get(symbol, price), 1e-9)
                peak = max(peak_price_since_entry.get(symbol, price), price)
                stop_price, trailing_stop_price, take_profit_price = _long_exit_levels(
                    entry,
                    peak,
                    history_by_symbol[symbol][:-1],
                    params,
                )
                if float(bar.low) <= stop_price:
                    close_position(
                        symbol,
                        bar,
                        f"portfolio risk exit: ATR/fixed stop hit at stop level ({(stop_price / entry) - 1:.2%}); {signal.reason}",
                        execution_price=stop_price,
                    )
                    latest_price[symbol] = stop_price
                    continue
                if float(bar.low) <= trailing_stop_price:
                    close_position(
                        symbol,
                        bar,
                        f"portfolio risk exit: ATR/fixed trailing stop hit at stop level ({(trailing_stop_price / peak) - 1:.2%}); {signal.reason}",
                        execution_price=trailing_stop_price,
                    )
                    latest_price[symbol] = trailing_stop_price
                    continue
                if float(bar.high) >= take_profit_price:
                    close_position(
                        symbol,
                        bar,
                        f"portfolio risk exit: take profit hit at {params.take_profit_r_multiple:.1f}R; {signal.reason}",
                        execution_price=take_profit_price,
                    )
                    latest_price[symbol] = take_profit_price
                    continue
                if signal.action == "SELL":
                    close_position(symbol, bar, signal.reason)
                    continue

            if signal.action == "BUY" and held_qty <= 0:
                buy_candidates.append((signal.confidence, symbol, bar, signal))

        open_positions = sum(1 for qty in positions.values() if qty > 0)
        available_slots = max(0, int(params.max_positions) - open_positions)
        for _, symbol, bar, signal in sorted(buy_candidates, key=lambda item: (-item[0], item[1]))[:available_slots]:
            price = float(bar.close)
            notional = min(signal.target_notional if signal.target_notional > 0 else float(trade_notional), cash)
            if price <= 0 or notional <= 0:
                continue
            qty = notional / price
            cash -= notional
            positions[symbol] = qty
            entry_notional[symbol] = notional
            entry_price[symbol] = price
            peak_price_since_entry[symbol] = price
            trades.append(
                BacktestTrade(
                    timestamp=bar.timestamp,
                    symbol=symbol,
                    side="buy",
                    qty=round(qty, 8),
                    price=round(price, 4),
                    notional=round(notional, 4),
                    reason=f"ranked buy candidate confidence={signal.confidence:.2f}; {signal.reason}",
                )
            )

        positions_value = sum(positions[symbol] * latest_price.get(symbol, 0.0) for symbol in positions)
        equity = cash + positions_value
        equity_curve.append(
            BacktestEquityPoint(
                timestamp=next(iter(day_bars.values())).timestamp,
                equity=round(equity, 4),
                cash=round(cash, 4),
                position_qty=round(sum(1 for qty in positions.values() if qty > 0), 8),
                close=round(positions_value, 4),
            )
        )

    final_equity = equity_curve[-1].equity if equity_curve else round(float(initial_cash), 4)
    exposure_pct = (
        sum(1 for point in equity_curve if point.position_qty > 0) / len(equity_curve)
        if equity_curve
        else 0.0
    )
    hold_returns = [bars[-1].close / bars[0].close - 1 for bars in ordered.values() if len(bars) >= 2 and bars[0].close > 0]
    buy_and_hold_return = sum(hold_returns) / len(hold_returns) if hold_returns else 0.0
    win_rate = (winning_round_trips / closed_round_trips) if closed_round_trips else None
    diagnostics = _trade_quality_metrics(trades)

    metrics = BacktestMetrics(
        total_return=round((final_equity / float(initial_cash)) - 1, 6),
        final_equity=round(final_equity, 4),
        max_drawdown=round(calculate_max_drawdown([point.equity for point in equity_curve]), 6),
        trades_count=len(trades),
        win_rate=round(win_rate, 6) if win_rate is not None else None,
        exposure_pct=round(exposure_pct, 6),
        buy_and_hold_return=round(float(buy_and_hold_return), 6),
        **diagnostics,
    )

    return BacktestResult(
        symbol="WATCHLIST_PORTFOLIO",
        strategy_name=MovingAverageCrossoverStrategy.name,
        params=StrategyParamsModel(**params.__dict__),
        initial_cash=float(initial_cash),
        trade_notional=float(trade_notional),
        last_signal=last_signal,
        trades=trades,
        equity_curve=equity_curve,
        metrics=metrics,
    )
