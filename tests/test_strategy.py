from datetime import UTC, datetime, timedelta

from trading_app.schemas import Bar
from trading_app.strategy import MovingAverageCrossoverStrategy, StrategyParams


def bars_from_prices(prices: list[float]) -> list[Bar]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Bar(
            symbol="AAPL",
            timestamp=start + timedelta(days=index),
            open=price,
            high=price,
            low=price,
            close=price,
            volume=100,
        )
        for index, price in enumerate(prices)
    ]


def test_strategy_emits_buy_for_positive_crossover() -> None:
    strategy = MovingAverageCrossoverStrategy(StrategyParams(short_window=2, long_window=4, min_crossover_pct=0.001))
    signal = strategy.generate_signal("AAPL", bars_from_prices([10, 10, 12, 13]))

    assert signal.action == "BUY"
    assert signal.confidence > 0


def test_strategy_holds_without_enough_data() -> None:
    strategy = MovingAverageCrossoverStrategy(StrategyParams(short_window=2, long_window=4))
    signal = strategy.generate_signal("AAPL", bars_from_prices([10, 11, 12]))

    assert signal.action == "HOLD"


def test_strategy_avoids_buying_overextended_drawdowns() -> None:
    strategy = MovingAverageCrossoverStrategy(
        StrategyParams(
            short_window=2,
            long_window=4,
            min_crossover_pct=0.001,
            momentum_window=3,
            volatility_window=3,
            min_momentum_pct=0.0,
            max_drawdown_from_peak_pct=0.10,
        )
    )

    signal = strategy.generate_signal("AAPL", bars_from_prices([10, 15, 14, 13, 12]))

    assert signal.action == "SELL"
    assert "drawdown" in signal.reason.lower()


def test_intraday_strategy_sizes_risk_lower_when_volatility_is_high() -> None:
    stable_strategy = MovingAverageCrossoverStrategy(
        StrategyParams(short_window=3, long_window=6, momentum_window=4, volatility_window=4, min_momentum_pct=0.001)
    )
    volatile_strategy = MovingAverageCrossoverStrategy(
        StrategyParams(short_window=3, long_window=6, momentum_window=4, volatility_window=4, min_momentum_pct=0.001)
    )

    stable_signal = stable_strategy.generate_signal("MSFT", bars_from_prices([100, 100.5, 101, 101.5, 102, 103, 104, 105]))
    volatile_signal = volatile_strategy.generate_signal("NVDA", bars_from_prices([100, 108, 96, 112, 102, 116, 106, 120]))

    assert stable_signal.action == "BUY"
    assert stable_signal.timeframe == "intraday_5min"
    assert stable_signal.strategy_mode == "intraday_long_only_no_leverage"
    assert stable_signal.risk_fraction > volatile_signal.risk_fraction
    assert stable_signal.target_notional > volatile_signal.target_notional
    assert "no leverage" in stable_signal.reason.lower()


def test_strategy_sell_signal_is_long_exit_not_short_entry() -> None:
    strategy = MovingAverageCrossoverStrategy(StrategyParams(short_window=2, long_window=4, max_drawdown_from_peak_pct=0.1))

    signal = strategy.generate_signal("MSFT", bars_from_prices([100, 110, 109, 108, 90]))

    assert signal.action == "SELL"
    assert signal.strategy_mode == "intraday_long_only_no_leverage"
    assert signal.risk_fraction == 0.0
    assert signal.target_notional == 0.0
    assert "exit only" in signal.reason.lower()
