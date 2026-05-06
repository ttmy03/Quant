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
    assert stable_signal.strategy_mode == "stock_watchlist_adam_eve_vwap_adaptive_risk"
    assert stable_signal.risk_fraction > volatile_signal.risk_fraction
    assert stable_signal.target_notional > volatile_signal.target_notional
    assert "no leverage" in stable_signal.reason.lower()


def test_strategy_sell_signal_is_long_exit_not_short_entry() -> None:
    strategy = MovingAverageCrossoverStrategy(StrategyParams(short_window=2, long_window=4, max_drawdown_from_peak_pct=0.1))

    signal = strategy.generate_signal("MSFT", bars_from_prices([100, 110, 109, 108, 90]))

    assert signal.action == "SELL"
    assert signal.strategy_mode == "stock_watchlist_adam_eve_vwap_adaptive_risk"
    assert signal.risk_fraction == 0.0
    assert signal.target_notional == 0.0
    assert "exit only" in signal.reason.lower()


def test_strategy_v2_requires_price_above_vwap_for_new_long_entries() -> None:
    strategy = MovingAverageCrossoverStrategy(
        StrategyParams(
            short_window=2,
            long_window=4,
            min_crossover_pct=0.001,
            momentum_window=3,
            min_momentum_pct=0.001,
            vwap_window=4,
        )
    )
    bars = bars_from_prices([100, 100, 110, 115, 104])
    bars[-1].volume = 10

    signal = strategy.generate_signal("MSFT", bars)

    assert signal.action != "BUY"
    assert "vwap" in signal.reason.lower()


def test_strategy_v2_buy_reason_mentions_vwap_atr_and_relative_strength() -> None:
    strategy = MovingAverageCrossoverStrategy(
        StrategyParams(short_window=2, long_window=4, min_crossover_pct=0.001, momentum_window=3, min_momentum_pct=0.001)
    )

    signal = strategy.generate_signal("MSFT", bars_from_prices([100, 100, 101, 102, 103, 104, 106, 108]))

    assert signal.action == "BUY"
    assert signal.strategy_mode == "stock_watchlist_adam_eve_vwap_adaptive_risk"
    assert "vwap" in signal.reason.lower()
    assert "atr" in signal.reason.lower()
    assert "relative strength" in signal.reason.lower()


def test_strategy_v2_default_buy_score_ignores_weak_intraday_edges() -> None:
    strategy = MovingAverageCrossoverStrategy(
        StrategyParams(short_window=2, long_window=4, min_crossover_pct=0.001, momentum_window=3, min_momentum_pct=0.001)
    )

    signal = strategy.generate_signal("MSFT", bars_from_prices([100, 100, 100, 100, 100.3, 100.5, 100.7, 100.9]))

    assert signal.action == "HOLD"
    assert "no strong risk-adjusted long edge" in signal.reason.lower()


def test_stock_watchlist_adam_eve_reversal_requires_flush_and_recovery() -> None:
    strategy = MovingAverageCrossoverStrategy(
        StrategyParams(
            short_window=4,
            long_window=12,
            momentum_window=8,
            volatility_window=8,
            min_momentum_pct=0.001,
            min_buy_score=10.0,
            max_drawdown_from_peak_pct=0.50,
            adam_eve_rsi_reversal=45.0,
            adam_eve_volume_mult=0.5,
            adam_eve_ema200_floor=0.70,
            adam_eve_min_drawdown_pct=0.025,
        )
    )
    prices = [100 + index * 0.05 for index in range(60)]
    prices += [102, 101, 100, 99, 98, 97.5, 97, 96.5, 96, 95.5, 95, 94.5]
    bars = bars_from_prices(prices)
    bars[-1].open = 96.0
    bars[-1].low = 91.5
    bars[-1].high = 98.0
    bars[-1].close = 96.5
    bars[-1].volume = 400

    signal = strategy.generate_signal("MSFT", bars)

    assert signal.action == "BUY"
    assert signal.strategy_mode == "stock_watchlist_adam_eve_vwap_adaptive_risk"
    assert "adam/eve" in signal.reason.lower()
    assert "adam_eve_reversal" in signal.reason
    assert signal.target_notional > 0


def test_stock_watchlist_adam_eve_filter_blocks_illiquid_reversal() -> None:
    strategy = MovingAverageCrossoverStrategy(
        StrategyParams(
            short_window=4,
            long_window=12,
            min_buy_score=10.0,
            adam_eve_rsi_reversal=45.0,
            adam_eve_volume_mult=3.0,
            adam_eve_ema200_floor=0.70,
            adam_eve_min_drawdown_pct=0.025,
        )
    )
    prices = [100 + index * 0.05 for index in range(60)] + [102, 101, 100, 99, 98, 97.5, 97, 96.5, 96, 95.5, 95, 94.5]
    bars = bars_from_prices(prices)
    bars[-1].open = 96.0
    bars[-1].low = 91.5
    bars[-1].high = 98.0
    bars[-1].close = 96.5
    bars[-1].volume = 100

    signal = strategy.generate_signal("MSFT", bars)

    assert signal.action != "BUY"


def test_recursive_improver_preserves_adam_eve_parameters_when_proposing_candidates() -> None:
    from trading_app.config import Settings
    from trading_app.improver import RecursiveImprover

    base = StrategyParams(
        short_window=8,
        long_window=30,
        adam_eve_enabled=False,
        adam_eve_rsi_reversal=44.0,
        adam_eve_volume_mult=1.25,
        adam_eve_pullback_symbols=("MSFT", "NVDA"),
    )

    candidates = RecursiveImprover(Settings(auth_enabled=False)).propose_candidates(base)

    assert candidates
    assert all(candidate.adam_eve_enabled is False for candidate in candidates)
    assert all(candidate.adam_eve_rsi_reversal == 44.0 for candidate in candidates)
    assert all(candidate.adam_eve_volume_mult == 1.25 for candidate in candidates)
    assert all(candidate.adam_eve_pullback_symbols == ("MSFT", "NVDA") for candidate in candidates)
