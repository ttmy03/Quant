from __future__ import annotations

from typing import Any

from trading_app.alpaca import AlpacaClient
from trading_app.config import Settings
from trading_app.data import generate_synthetic_bars
from trading_app.risk import RiskGuard
from trading_app.schemas import OrderIntent, SchedulerRunRequest
from trading_app.storage import Storage
from trading_app.strategy import MovingAverageCrossoverStrategy, StrategyParams
from trading_app.watchlist import build_dynamic_halal_watchlist


class DryRunSchedulerService:
    """Runs one paper-only trading cycle and records every decision locally."""

    def __init__(self, settings: Settings, storage: Storage, strategy_params: StrategyParams) -> None:
        self.settings = settings
        self.storage = storage
        self.strategy_params = strategy_params

    def run_once(self, request: SchedulerRunRequest) -> dict[str, Any]:
        effective_settings = self.settings.model_copy(
            update={"dry_run": True, "paper_trading_only": True}
        )
        client = AlpacaClient(effective_settings)
        watchlist_payload: dict[str, Any] | None = None
        if request.symbols:
            symbols = [symbol.upper() for symbol in request.symbols]
        else:
            watchlist_payload = build_dynamic_halal_watchlist(client, limit=250)
            symbols = [symbol.upper() for symbol in watchlist_payload["symbols"]]
            if not symbols:
                symbols = list(self.settings.default_symbols)
        effective_settings = effective_settings.model_copy(update={"default_symbols": tuple(symbols)})
        client = AlpacaClient(effective_settings)
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
                "watchlist": watchlist_payload,
            }

        account = client.account_status()
        available_cash = float(account.get("cash") or account.get("buying_power") or self.strategy_params.account_equity)
        account_equity = float(account.get("equity") or account.get("portfolio_value") or self.strategy_params.account_equity)
        risk_guard = RiskGuard(effective_settings)
        strategy = MovingAverageCrossoverStrategy(
            StrategyParams(**{**self.strategy_params.__dict__, "account_equity": max(account_equity, 1.0)})
        )
        signal_records: list[dict[str, Any]] = []
        order_records: list[dict[str, Any]] = []

        for index, symbol in enumerate(symbols):
            timeframe = getattr(getattr(strategy, "params", None), "intraday_timeframe", "5Min")
            bars = client.historical_bars(symbol, days=request.lookback_days, timeframe=timeframe)
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
                estimated_price = bars[-1].close if bars else 0.0
                target_notional = signal.target_notional if signal.action == "BUY" and signal.target_notional > 0 else request.qty * estimated_price
                qty = max(0.000001, target_notional / max(float(estimated_price), 1e-9))
                intent = OrderIntent(symbol=symbol, side=signal.action.lower(), qty=qty)
                risk_decision = risk_guard.evaluate_order(
                    intent,
                    estimated_price=estimated_price,
                    available_cash=available_cash,
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
            "watchlist": watchlist_payload,
        }
