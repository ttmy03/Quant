from datetime import UTC, datetime, timedelta

from trading_app.backtest import run_backtest, run_portfolio_backtest
from trading_app.schemas import Bar
from trading_app.storage import Storage
from trading_app.strategy import StrategyParams


def bars_from_prices(prices: list[float], symbol: str = "AAPL") -> list[Bar]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Bar(
            symbol=symbol,
            timestamp=start + timedelta(days=index),
            open=price,
            high=price,
            low=price,
            close=price,
            volume=100,
        )
        for index, price in enumerate(prices)
    ]


def intraday_bars_from_prices(prices: list[float], symbol: str = "AAPL") -> list[Bar]:
    start = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    return [
        Bar(
            symbol=symbol,
            timestamp=start + timedelta(minutes=5 * index),
            open=price,
            high=price + 0.2,
            low=price - 0.2,
            close=price,
            volume=1_000 + index,
        )
        for index, price in enumerate(prices)
    ]


def test_backtest_holds_without_enough_data() -> None:
    result = run_backtest(
        bars_from_prices([10, 11, 12]),
        StrategyParams(short_window=2, long_window=4),
        initial_cash=10_000,
        trade_notional=1_000,
    )

    assert result.last_signal.action == "HOLD"
    assert result.trades == []
    assert result.metrics.trades_count == 0
    assert result.metrics.final_equity == 10_000
    assert len(result.equity_curve) == 3


def test_backtest_positive_trend_reports_sensible_metrics() -> None:
    result = run_backtest(
        bars_from_prices([10, 10, 10, 10, 11, 12, 13, 14, 15, 16]),
        StrategyParams(short_window=2, long_window=4, min_crossover_pct=0.001),
        initial_cash=10_000,
        trade_notional=1_000,
    )

    assert result.metrics.final_equity > 10_000
    assert result.metrics.total_return > 0
    assert result.metrics.buy_and_hold_return > 0
    assert result.metrics.trades_count == 1
    assert result.trades[0].side == "buy"
    assert 0 < result.metrics.exposure_pct <= 1


def test_portfolio_backtest_runs_all_tickers_and_records_all_trades() -> None:
    result = run_portfolio_backtest(
        {
            "ALGM": bars_from_prices([10, 10, 10, 10, 11, 12, 13, 14, 13, 12], "ALGM"),
            "AMKR": bars_from_prices([20, 20, 20, 20, 22, 24, 26, 28, 26, 24], "AMKR"),
            "TREX": bars_from_prices([30, 30, 30, 30, 33, 36, 39, 42, 39, 36], "TREX"),
        },
        StrategyParams(short_window=2, long_window=4, min_crossover_pct=0.001),
        initial_cash=10_000,
        trade_notional=1_000,
    )

    traded_symbols = {trade.symbol for trade in result.trades}
    assert result.symbol == "WATCHLIST_PORTFOLIO"
    assert {"ALGM", "AMKR", "TREX"}.issubset(traded_symbols)
    assert result.metrics.trades_count == len(result.trades)
    assert len(result.equity_curve) == 10
    assert result.equity_curve[-1].equity > 0


def test_portfolio_backtest_limits_positions_to_highest_confidence_signals() -> None:
    result = run_portfolio_backtest(
        {
            "SLOW": bars_from_prices([10, 10, 10, 10, 10.5, 11, 11.2, 11.4], "SLOW"),
            "FAST": bars_from_prices([10, 10, 10, 10, 12, 14, 16, 18], "FAST"),
            "MID": bars_from_prices([10, 10, 10, 10, 11, 12, 13, 14], "MID"),
        },
        StrategyParams(
            short_window=2,
            long_window=4,
            min_crossover_pct=0.001,
            momentum_window=3,
            max_positions=2,
        ),
        initial_cash=10_000,
        trade_notional=1_000,
    )

    bought_symbols = [trade.symbol for trade in result.trades if trade.side == "buy"]
    assert "FAST" in bought_symbols[:2]
    assert max(point.position_qty for point in result.equity_curve) <= 2


def test_portfolio_backtest_ranks_strong_setup_above_alphabetical_weak_setup() -> None:
    result = run_portfolio_backtest(
        {
            "ALPHAWEAK": bars_from_prices([100, 100, 100, 100, 100.3, 100.5, 100.7, 100.9], "ALPHAWEAK"),
            "ZSTRONG": bars_from_prices([100, 100, 101, 102, 103, 104, 106, 108], "ZSTRONG"),
        },
        StrategyParams(
            short_window=2,
            long_window=4,
            min_crossover_pct=0.001,
            momentum_window=3,
            min_momentum_pct=0.001,
            min_buy_score=0.75,
            max_positions=1,
        ),
        initial_cash=10_000,
        trade_notional=1_000,
    )

    bought_symbols = [trade.symbol for trade in result.trades if trade.side == "buy"]
    assert bought_symbols[0] == "ZSTRONG"
    assert max(point.position_qty for point in result.equity_curve) <= 1


def test_storage_roundtrips_backtest_result(tmp_path) -> None:
    storage = Storage(tmp_path / "test.sqlite3")
    result = run_backtest(
        bars_from_prices([10, 10, 10, 10, 11, 12, 13, 14]),
        StrategyParams(short_window=2, long_window=4),
    )

    record = storage.record_backtest(
        name="moving_average_crossover",
        symbol=result.symbol,
        inputs={"symbol": result.symbol, "initial_cash": result.initial_cash},
        metrics=result.metrics.model_dump(),
        trades=[trade.model_dump(mode="json") for trade in result.trades],
        equity_curve=[point.model_dump(mode="json") for point in result.equity_curve],
    )
    latest = storage.list_backtests(limit=1)

    assert record["id"] is not None
    assert latest[0]["symbol"] == "AAPL"
    assert latest[0]["metrics"]["final_equity"] == result.metrics.final_equity
    assert latest[0]["trades"] == [trade.model_dump(mode="json") for trade in result.trades]


def test_portfolio_backtest_steps_through_intraday_timestamps_not_only_dates() -> None:
    result = run_portfolio_backtest(
        {
            "FAST": intraday_bars_from_prices([10, 10, 10, 10, 11, 12, 13, 14], "FAST"),
            "SLOW": intraday_bars_from_prices([20, 20, 20, 20, 20.5, 21, 21.5, 22], "SLOW"),
        },
        StrategyParams(short_window=2, long_window=4, min_crossover_pct=0.001),
        initial_cash=10_000,
        trade_notional=1_000,
    )

    assert len(result.equity_curve) == 8
    assert result.equity_curve[1].timestamp > result.equity_curve[0].timestamp


def test_portfolio_backtest_reports_trade_quality_diagnostics() -> None:
    result = run_portfolio_backtest(
        {
            "WIN": bars_from_prices([10, 10, 10, 10, 11, 12, 13, 14, 15], "WIN"),
            "LOSE": bars_from_prices([20, 20, 20, 20, 22, 18, 17, 16, 15], "LOSE"),
        },
        StrategyParams(short_window=2, long_window=4, min_crossover_pct=0.001, stop_loss_pct=0.08),
        initial_cash=10_000,
        trade_notional=1_000,
    )

    assert result.metrics.profit_factor is not None
    assert result.metrics.avg_loser is not None
    assert result.metrics.per_symbol_pnl
    assert set(result.metrics.per_symbol_pnl).issubset({"WIN", "LOSE"})



def test_portfolio_backtest_executes_stop_loss_at_stop_level_not_bad_close() -> None:
    result = run_portfolio_backtest(
        {
            "GAP": bars_from_prices([100, 100, 100, 100, 110, 111, 80], "GAP"),
        },
        StrategyParams(
            short_window=2,
            long_window=4,
            min_crossover_pct=0.001,
            stop_loss_pct=0.05,
            trailing_stop_pct=0.50,
            max_positions=1,
        ),
        initial_cash=10_000,
        trade_notional=1_000,
    )

    stop_trades = [trade for trade in result.trades if trade.side == "sell" and "stop" in trade.reason.lower()]
    assert stop_trades
    assert stop_trades[-1].price > 80
    assert stop_trades[-1].price < 111
    assert result.metrics.max_drawdown < 0.03


def test_portfolio_backtest_takes_profit_at_configured_r_multiple() -> None:
    result = run_portfolio_backtest(
        {
            "TP": bars_from_prices([100, 100, 100, 100, 110, 111, 116, 117], "TP"),
        },
        StrategyParams(
            short_window=2,
            long_window=4,
            min_crossover_pct=0.001,
            stop_loss_pct=0.05,
            trailing_stop_pct=0.50,
            take_profit_r_multiple=1.0,
            max_positions=1,
        ),
        initial_cash=10_000,
        trade_notional=1_000,
    )

    sell_trades = [trade for trade in result.trades if trade.side == "sell"]
    assert sell_trades
    assert "take profit" in sell_trades[-1].reason.lower()
    assert sell_trades[-1].price > result.trades[0].price
    assert result.metrics.profit_factor is not None
    assert result.metrics.profit_factor > 0
