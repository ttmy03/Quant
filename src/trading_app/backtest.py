from __future__ import annotations

from collections.abc import Sequence

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
