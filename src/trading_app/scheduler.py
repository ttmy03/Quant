from __future__ import annotations

from typing import Any

from trading_app.alpaca import AlpacaClient
from trading_app.config import Settings
from trading_app.data import generate_synthetic_bars
from trading_app.risk import RiskGuard
from trading_app.schemas import OrderIntent, SchedulerRunRequest
from trading_app.storage import Storage
from trading_app.strategy import MovingAverageCrossoverStrategy, StrategyParams


class DryRunSchedulerService:
    """Runs one paper-only trading cycle and records every decision locally."""

    def __init__(self, settings: Settings, storage: Storage, strategy_params: StrategyParams) -> None:
        self.settings = settings
        self.storage = storage
        self.strategy_params = strategy_params

    def run_once(self, request: SchedulerRunRequest) -> dict[str, Any]:
        symbols = request.symbols or list(self.settings.default_symbols)
        symbols = [symbol.upper() for symbol in symbols]
        effective_settings = self.settings.model_copy(
            update={"dry_run": True, "paper_trading_only": True}
        )
        run = self.storage.start_scheduler_run(
            dry_run=True,
            paper_trading_only=True,
            symbols=symbols,
        )
        control = self.storage.get_trading_control_state()
        if not control["can_trade"]:
            blocked_reason = "kill switch active" if control["kill_switch_active"] else "trading paused"
            run = self.storage.complete_scheduler_run(
                run["id"],
                status="blocked_by_control",
                signals_count=0,
                orders_count=0,
                blocked_reason=blocked_reason,
            )
            self.storage.record_audit(
                "scheduler_run_blocked",
                "Dry-run scheduler was blocked by trading control state.",
                {"scheduler_run_id": run["id"], "control": control, "blocked_reason": blocked_reason},
                actor="scheduler",
            )
            return {
                "run": run,
                "signals": [],
                "orders": [],
                "control": control,
                "no_live_orders_sent": True,
            }

        client = AlpacaClient(effective_settings)
        risk_guard = RiskGuard(effective_settings)
        strategy = MovingAverageCrossoverStrategy(self.strategy_params)
        signal_records: list[dict[str, Any]] = []
        order_records: list[dict[str, Any]] = []

        for index, symbol in enumerate(symbols):
            bars = client.historical_bars(symbol, days=request.lookback_days)
            source = "alpaca"
            if not bars:
                bars = generate_synthetic_bars(
                    symbol=symbol,
                    days=request.lookback_days,
                    seed=request.seed + index,
                )
                source = "synthetic_fallback"

            signal = strategy.generate_signal(symbol, bars)
            order_record: dict[str, Any] | None = None
            if signal.action in {"BUY", "SELL"}:
                intent = OrderIntent(symbol=symbol, side=signal.action.lower(), qty=request.qty)
                estimated_price = bars[-1].close if bars else 0.0
                risk_decision = risk_guard.evaluate_order(
                    intent,
                    estimated_price=estimated_price,
                    orders_today=len(self.storage.list_orders(limit=effective_settings.max_daily_orders)),
                )
                submission = client.place_order(intent, risk_decision)
                order_record = self.storage.record_order(
                    intent,
                    status=submission.status,
                    dry_run=True,
                    alpaca_order_id=submission.order_id,
                    raw_response={
                        "scheduler_run_id": run["id"],
                        "signal": signal.model_dump(),
                        "risk": risk_decision.model_dump(),
                        "submission": submission.model_dump(),
                    },
                    source="scheduler",
                    scheduler_run_id=run["id"],
                )
                order_records.append(order_record)

            signal_records.append(
                self.storage.record_scheduler_signal(
                    run["id"],
                    signal,
                    source=source,
                    order_id=order_record["id"] if order_record else None,
                )
            )

        run = self.storage.complete_scheduler_run(
            run["id"],
            status="completed",
            signals_count=len(signal_records),
            orders_count=len(order_records),
        )
        self.storage.record_audit(
            "scheduler_run_completed",
            "Dry-run scheduler cycle completed.",
            {
                "scheduler_run_id": run["id"],
                "signals_count": len(signal_records),
                "orders_count": len(order_records),
                "symbols": symbols,
                "no_live_orders_sent": True,
            },
            actor="scheduler",
        )
        return {
            "run": run,
            "signals": signal_records,
            "orders": order_records,
            "control": control,
            "no_live_orders_sent": True,
        }
