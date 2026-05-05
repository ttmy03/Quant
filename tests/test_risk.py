from trading_app.config import Settings
from trading_app.risk import RiskGuard
from trading_app.schemas import OrderIntent


def test_risk_guard_rejects_non_paper_endpoint_when_paper_only() -> None:
    settings = Settings(
        ALPACA_BASE_URL="https://api.alpaca.markets",
        PAPER_TRADING_ONLY=True,
        DEFAULT_SYMBOLS="AAPL",
    )
    decision = RiskGuard(settings).evaluate_order(
        OrderIntent(symbol="AAPL", side="buy", qty=1),
        estimated_price=100,
    )

    assert not decision.allowed
    assert "PAPER_TRADING_ONLY" in decision.reasons[0]


def test_risk_guard_rejects_oversized_order() -> None:
    settings = Settings(MAX_ORDER_NOTIONAL=50, DEFAULT_SYMBOLS="AAPL")
    decision = RiskGuard(settings).evaluate_order(
        OrderIntent(symbol="AAPL", side="buy", qty=1),
        estimated_price=100,
    )

    assert not decision.allowed
    assert any("MAX_ORDER_NOTIONAL" in reason for reason in decision.reasons)


def test_risk_guard_allows_small_paper_order() -> None:
    settings = Settings(DEFAULT_SYMBOLS="AAPL", MAX_ORDER_NOTIONAL=1000)
    decision = RiskGuard(settings).evaluate_order(
        OrderIntent(symbol="AAPL", side="buy", qty=1),
        estimated_price=100,
    )

    assert decision.allowed
    assert decision.estimated_notional == 100
