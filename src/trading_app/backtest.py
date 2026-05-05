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


def run_backtest(
    bars: Sequence[Bar],
    params: StrategyParams,
    *,
    initial_cash: float = 10_000.0,
    trade_notional: float = 1_000.0,
) -> BacktestResult:
    """Run a deterministic long-only moving-average crossover backtest."""

    strategy = MovingAverageCrossoverStrategy(params)
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
            notional = min(float(trade_notional), cash)
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

    metrics = BacktestMetrics(
        total_return=round((final_equity / float(initial_cash)) - 1, 6),
        final_equity=round(final_equity, 4),
        max_drawdown=round(calculate_max_drawdown([point.equity for point in equity_curve]), 6),
        trades_count=len(trades),
        win_rate=round(win_rate, 6) if win_rate is not None else None,
        exposure_pct=round(exposure_pct, 6),
        buy_and_hold_return=round(float(buy_and_hold_return), 6),
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

    strategy = MovingAverageCrossoverStrategy(params)
    ordered: dict[str, list[Bar]] = {
        symbol.upper(): sorted(list(bars), key=lambda bar: bar.timestamp)
        for symbol, bars in bars_by_symbol.items()
        if bars
    }
    if not ordered:
        return run_backtest([], params, initial_cash=initial_cash, trade_notional=trade_notional)

    bars_by_date: dict[object, dict[str, Bar]] = defaultdict(dict)
    history_by_symbol: dict[str, list[Bar]] = {symbol: [] for symbol in ordered}
    latest_price: dict[str, float] = {}
    for symbol, bars in ordered.items():
        for bar in bars:
            bars_by_date[bar.timestamp.date()][symbol] = bar

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

    def close_position(symbol: str, bar: Bar, reason: str) -> None:
        nonlocal cash, winning_round_trips, closed_round_trips
        qty = positions.get(symbol, 0.0)
        price = float(bar.close)
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

    for day in sorted(bars_by_date):
        day_bars = bars_by_date[day]
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
                loss_from_entry = (price / entry) - 1
                trailing_drawdown = (price / peak) - 1
                if loss_from_entry <= -params.stop_loss_pct:
                    close_position(
                        symbol,
                        bar,
                        f"portfolio risk exit: stop loss hit ({loss_from_entry:.2%}); {signal.reason}",
                    )
                    continue
                if trailing_drawdown <= -params.trailing_stop_pct:
                    close_position(
                        symbol,
                        bar,
                        f"portfolio risk exit: trailing stop hit ({trailing_drawdown:.2%}); {signal.reason}",
                    )
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
            notional = min(float(trade_notional), cash)
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

    metrics = BacktestMetrics(
        total_return=round((final_equity / float(initial_cash)) - 1, 6),
        final_equity=round(final_equity, 4),
        max_drawdown=round(calculate_max_drawdown([point.equity for point in equity_curve]), 6),
        trades_count=len(trades),
        win_rate=round(win_rate, 6) if win_rate is not None else None,
        exposure_pct=round(exposure_pct, 6),
        buy_and_hold_return=round(float(buy_and_hold_return), 6),
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
