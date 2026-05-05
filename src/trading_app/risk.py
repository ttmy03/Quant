from __future__ import annotations

from trading_app.config import Settings
from trading_app.schemas import OrderIntent, RiskDecision


class RiskGuard:
    """Pre-trade guardrails for paper-first execution."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def evaluate_order(
        self,
        intent: OrderIntent,
        estimated_price: float,
        open_position_notional: float = 0.0,
        orders_today: int = 0,
    ) -> RiskDecision:
        reasons: list[str] = []
        estimated_notional = intent.qty * (intent.limit_price or estimated_price)

        if self.settings.paper_trading_only and not self.settings.is_paper_endpoint:
            reasons.append("PAPER_TRADING_ONLY blocks non-paper Alpaca endpoints")

        if self.settings.default_symbols and intent.symbol not in self.settings.default_symbols:
            reasons.append(f"{intent.symbol} is outside DEFAULT_SYMBOLS allowlist")

        if estimated_notional > self.settings.max_order_notional:
            reasons.append(
                f"order notional {estimated_notional:.2f} exceeds MAX_ORDER_NOTIONAL "
                f"{self.settings.max_order_notional:.2f}"
            )

        if open_position_notional + estimated_notional > self.settings.max_position_notional:
            reasons.append(
                "projected position notional exceeds MAX_POSITION_NOTIONAL "
                f"{self.settings.max_position_notional:.2f}"
            )

        if orders_today >= self.settings.max_daily_orders:
            reasons.append("MAX_DAILY_ORDERS limit reached")

        return RiskDecision(
            allowed=not reasons,
            reasons=reasons,
            estimated_notional=round(estimated_notional, 4),
        )

    def strategy_metrics_pass(
        self,
        max_drawdown: float,
        probability_of_ruin: float,
    ) -> RiskDecision:
        reasons: list[str] = []
        if max_drawdown > self.settings.max_strategy_drawdown:
            reasons.append(
                f"max drawdown {max_drawdown:.4f} exceeds limit "
                f"{self.settings.max_strategy_drawdown:.4f}"
            )
        if probability_of_ruin > self.settings.max_probability_of_ruin:
            reasons.append(
                f"probability of ruin {probability_of_ruin:.4f} exceeds limit "
                f"{self.settings.max_probability_of_ruin:.4f}"
            )
        return RiskDecision(allowed=not reasons, reasons=reasons)
