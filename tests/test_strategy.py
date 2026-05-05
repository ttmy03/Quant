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
