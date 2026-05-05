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
