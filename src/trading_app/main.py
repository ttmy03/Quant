from __future__ import annotations

from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from trading_app.alpaca import AlpacaClient
from trading_app.auth import AuthService, auth_state
from trading_app.backtest import run_backtest, run_portfolio_backtest
from trading_app.config import Settings, get_settings
from trading_app.data import generate_synthetic_bars, returns_from_bars
from trading_app.improver import RecursiveImprover
from trading_app.monte_carlo import simulate_portfolio_paths
from trading_app.risk import RiskGuard
from trading_app.schemas import (
    BacktestRequest,
    ClosePositionRequest,
    ControlReasonRequest,
    ImprovementRequest,
    KillSwitchRequest,
    MonteCarloRequest,
    OrderIntent,
    OrderSubmission,
    RiskDecision,
    SchedulerRunRequest,
    StrategyParamsModel,
)
from trading_app.scheduler import DryRunSchedulerService
from trading_app.storage import Storage
from trading_app.strategy import MovingAverageCrossoverStrategy, StrategyParams
from trading_app.watchlist import build_dynamic_halal_watchlist


STATIC_DIR = Path(__file__).parent / "static"
PUBLIC_AUTH_PATHS = {"/health", "/login", "/logout"}


def add_security_headers(response: Response) -> Response:
    response.headers["X-Trading-Disclaimer"] = "Research and paper trading only; not financial advice."
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


def build_alerts(storage: Storage, settings: Settings, limit: int = 50) -> list[dict[str, object]]:
    """Derive unresolved operator alerts from control state and recent audit events."""
    alerts: list[dict[str, object]] = []
    control = storage.get_trading_control_state()
    if control["kill_switch_active"]:
        alerts.append(
            {
                "severity": "critical",
                "category": "trading_control",
                "title": "Kill-Switch aktiv",
                "message": control.get("reason") or "Trading ist durch den Kill-Switch blockiert.",
                "created_at": control["updated_at"],
                "source": "trading_control_state",
            }
        )
    if control["paused"]:
        alerts.append(
            {
                "severity": "warning",
                "category": "trading_control",
                "title": "Trading pausiert",
                "message": control.get("reason") or "Trading ist manuell pausiert.",
                "created_at": control["updated_at"],
                "source": "trading_control_state",
            }
        )
    if not settings.dry_run or not settings.paper_trading_only:
        alerts.append(
            {
                "severity": "critical",
                "category": "safety",
                "title": "Safety-Flags pruefen",
                "message": "DRY_RUN und PAPER_TRADING_ONLY sollten fuer diese Phase aktiv bleiben.",
                "created_at": datetime.now(UTC).isoformat(),
                "source": "runtime_settings",
            }
        )

    event_alert_map = {
        "order_blocked_by_control": ("warning", "orders", "Order blockiert"),
        "scheduler_run_blocked": ("warning", "scheduler", "Scheduler blockiert"),
        "order_rejected": ("warning", "orders", "Order abgelehnt"),
        "kill_switch_enabled": ("critical", "trading_control", "Kill-Switch aktiviert"),
    }
    for event in storage.list_audit_events(limit=limit):
        mapped = event_alert_map.get(str(event["event_type"]))
        if mapped is None:
            continue
        severity, category, title = mapped
        alerts.append(
            {
                "severity": severity,
                "category": category,
                "title": title,
                "message": event["message"],
                "created_at": event["created_at"],
                "source": "audit_events",
                "audit_event_id": event["id"],
                "payload": event.get("payload", {}),
            }
        )
    return alerts[:limit]


def login_form(error: str | None = None, status_code: int = 200) -> HTMLResponse:
    error_html = f'<p class="error">{escape(error)}</p>' if error else ""
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Paper Quant Login</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f6f7f9;
        --panel: #ffffff;
        --ink: #1d2433;
        --muted: #647084;
        --line: #dce2ea;
        --accent: #0f766e;
        --danger: #b91c1c;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        align-items: center;
        background: var(--bg);
        color: var(--ink);
        display: flex;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        justify-content: center;
        margin: 0;
        min-height: 100vh;
        padding: 24px;
      }}
      main {{
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 8px;
        max-width: 380px;
        padding: 24px;
        width: 100%;
      }}
      h1 {{ font-size: 22px; margin: 0 0 6px; }}
      p {{ color: var(--muted); margin: 0 0 18px; }}
      label {{ display: grid; gap: 6px; margin-bottom: 12px; }}
      input, button {{
        border: 1px solid var(--line);
        border-radius: 6px;
        font: inherit;
        min-height: 40px;
        padding: 0 10px;
        width: 100%;
      }}
      button {{
        background: var(--accent);
        color: #fff;
        cursor: pointer;
      }}
      .error {{ color: var(--danger); }}
    </style>
  </head>
  <body>
    <main>
      <h1>Paper Quant</h1>
      <p>Sign in to access the dashboard and API.</p>
      {error_html}
      <form method="post" action="/login">
        <label>
          Username
          <input name="username" autocomplete="username" required />
        </label>
        <label>
          Password
          <input name="password" type="password" autocomplete="current-password" required />
        </label>
        <button type="submit">Sign in</button>
      </form>
    </main>
  </body>
</html>""",
        status_code=status_code,
    )


async def parse_urlencoded_form(request: Request) -> dict[str, str]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def create_app(settings: Settings | None = None, storage: Storage | None = None) -> FastAPI:
    settings = settings or get_settings()
    storage = storage or Storage(settings.database_path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        settings.validate_auth_configuration()
        yield

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Paper-first automated stock trading research app. Not financial advice.",
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.state.settings = settings
    app.state.storage = storage
    app.state.strategy_params = StrategyParams()
    app.state.auth = AuthService(settings)

    @app.middleware("http")
    async def enforce_auth_and_security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        if settings.auth_enabled and request.url.path not in PUBLIC_AUTH_PATHS:
            user = app.state.auth.read_session(request)
            if user is None:
                if request.url.path.startswith("/api"):
                    return add_security_headers(JSONResponse({"detail": "Authentication required."}, status_code=401))
                return add_security_headers(RedirectResponse(url="/login", status_code=303))
            request.state.user = user
        else:
            request.state.user = None

        response = await call_next(request)
        return add_security_headers(response)

    @app.get("/")
    def dashboard() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/login")
    def login(request: Request) -> Response:
        if settings.auth_enabled and app.state.auth.read_session(request):
            return RedirectResponse(url="/", status_code=303)
        return login_form()

    @app.post("/login")
    async def submit_login(request: Request) -> Response:
        if not settings.auth_enabled:
            return RedirectResponse(url="/", status_code=303)

        form = await parse_urlencoded_form(request)
        username = form.get("username", "")
        password = form.get("password", "")
        if not app.state.auth.authenticate(username, password):
            return login_form("Invalid username or password.", status_code=401)

        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            key=settings.session_cookie_name,
            value=app.state.auth.create_session_cookie(username),
            max_age=settings.session_max_age_seconds,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return response

    @app.post("/logout")
    def logout() -> RedirectResponse:
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie(settings.session_cookie_name, path="/")
        return response

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "dry_run": settings.dry_run,
            "paper_trading_only": settings.paper_trading_only,
            "alpaca_configured": settings.alpaca_configured,
        }

    @app.get("/api/config")
    def config() -> dict[str, object]:
        return settings.public_dict()

    @app.get("/api/auth/me")
    def auth_me(request: Request) -> dict[str, object]:
        user = getattr(request.state, "user", None)
        return auth_state(settings, user)

    @app.get("/api/portfolio/status")
    def portfolio_status() -> dict[str, object]:
        return AlpacaClient(settings).portfolio_status(settings.default_symbols)

    @app.get("/api/portfolio/positions")
    def portfolio_positions() -> dict[str, object]:
        return AlpacaClient(settings).positions()

    @app.get("/api/watchlist")
    def watchlist(limit: Annotated[int, Query(ge=1, le=300)] = 250) -> dict[str, object]:
        return build_dynamic_halal_watchlist(AlpacaClient(settings), limit=limit)

    @app.get("/api/trading-control")
    def trading_control() -> dict[str, object]:
        return storage.get_trading_control_state()

    @app.post("/api/trading-control/kill-switch")
    def set_kill_switch(request: KillSwitchRequest) -> dict[str, object]:
        state = storage.update_trading_control_state(
            kill_switch_active=request.enabled,
            reason=request.reason,
            actor="operator",
        )
        event_type = "kill_switch_enabled" if request.enabled else "kill_switch_disabled"
        storage.record_audit(
            event_type,
            "Kill switch enabled." if request.enabled else "Kill switch disabled.",
            {"reason": request.reason, "state": state},
            actor="operator",
        )
        return state

    @app.post("/api/trading-control/pause")
    def pause_trading(request: ControlReasonRequest) -> dict[str, object]:
        state = storage.update_trading_control_state(
            paused=True,
            reason=request.reason,
            actor="operator",
        )
        storage.record_audit(
            "trading_paused",
            "Trading paused.",
            {"reason": request.reason, "state": state},
            actor="operator",
        )
        return state

    @app.post("/api/trading-control/resume")
    def resume_trading(request: ControlReasonRequest) -> dict[str, object]:
        state = storage.update_trading_control_state(
            paused=False,
            reason=request.reason,
            actor="operator",
        )
        storage.record_audit(
            "trading_resumed",
            "Trading resumed.",
            {"reason": request.reason, "state": state},
            actor="operator",
        )
        return state

    @app.get("/api/orders")
    def orders(limit: Annotated[int, Query(ge=1, le=500)] = 100) -> list[dict[str, object]]:
        return storage.list_orders(limit=limit)

    @app.post("/api/orders")
    def submit_order(intent: OrderIntent) -> dict[str, object]:
        control = storage.get_trading_control_state()
        if not control["can_trade"]:
            submission = OrderSubmission(
                accepted=False,
                status="blocked_by_control",
                dry_run=True,
                message="Trading control state blocks order submission.",
                raw_response={"control": control},
            )
            storage.record_audit(
                "order_blocked_by_control",
                submission.message,
                {"intent": intent.model_dump(), "submission": submission.model_dump(), "control": control},
                actor="operator",
            )
            return {
                "order": None,
                "risk": {"allowed": False, "reasons": ["trading control state blocks orders"], "estimated_notional": 0.0},
                "submission": submission.model_dump(),
            }

        client = AlpacaClient(settings)
        bars = client.latest_bars([intent.symbol])
        estimated_price = bars[0].close if bars else intent.limit_price or 0.0
        orders_today = len(storage.list_orders(limit=settings.max_daily_orders))
        risk_decision = RiskGuard(settings).evaluate_order(
            intent,
            estimated_price=estimated_price,
            orders_today=orders_today,
        )
        submission = client.place_order(intent, risk_decision)
        order = storage.record_order(
            intent,
            status=submission.status,
            dry_run=submission.dry_run,
            alpaca_order_id=submission.order_id,
            raw_response=submission.raw_response,
            source="manual",
        )
        storage.record_audit(
            "order_submitted" if submission.accepted else "order_rejected",
            submission.message,
            {
                "intent": intent.model_dump(),
                "risk": risk_decision.model_dump(),
                "submission": submission.model_dump(),
            },
            actor="codex",
        )
        return {
            "order": order,
            "risk": risk_decision.model_dump(),
            "submission": submission.model_dump(),
        }


    @app.post("/api/positions/{symbol}/close")
    def close_position(symbol: str, request: ClosePositionRequest) -> dict[str, object]:
        symbol = symbol.upper()
        control = storage.get_trading_control_state()
        if not control["can_trade"]:
            submission = OrderSubmission(
                accepted=False,
                status="blocked_by_control",
                dry_run=True,
                message="Trading control state blocks manual position close.",
                raw_response={"control": control},
            )
            storage.record_audit(
                "position_close_blocked_by_control",
                submission.message,
                {"symbol": symbol, "reason": request.reason, "submission": submission.model_dump(), "control": control},
                actor="operator",
            )
            return {
                "position": None,
                "order": None,
                "risk": {"allowed": False, "reasons": ["trading control state blocks orders"], "estimated_notional": 0.0},
                "submission": submission.model_dump(),
            }

        client = AlpacaClient(settings)
        positions_payload = client.positions()
        position = next(
            (row for row in positions_payload.get("positions", []) if str(row.get("symbol", "")).upper() == symbol),
            None,
        )
        if position is None or float(position.get("qty") or 0.0) == 0.0:
            submission = OrderSubmission(
                accepted=False,
                status="no_position",
                dry_run=True,
                message=f"No open position found for {symbol}.",
                raw_response={"positions_source": positions_payload.get("source")},
            )
            storage.record_audit(
                "position_close_no_position",
                submission.message,
                {"symbol": symbol, "reason": request.reason, "submission": submission.model_dump()},
                actor="operator",
            )
            return {
                "position": None,
                "order": None,
                "risk": {"allowed": False, "reasons": ["no open position found"], "estimated_notional": 0.0},
                "submission": submission.model_dump(),
            }

        qty = abs(float(position.get("qty") or 0.0))
        side = "buy" if str(position.get("side", "")).lower() == "short" else "sell"
        intent = OrderIntent(symbol=symbol, side=side, qty=qty, order_type="market")
        estimated_price = float(position.get("current_price") or 0.0)
        if estimated_price <= 0:
            bars = client.latest_bars([symbol])
            estimated_price = bars[0].close if bars else 0.0
        estimated_notional = round(qty * estimated_price, 4)
        risk_decision = RiskDecision(
            allowed=True,
            reasons=["manual position close is risk-reducing; entry risk limits bypassed"],
            estimated_notional=estimated_notional,
        )
        submission = client.place_order(intent, risk_decision)
        order = storage.record_order(
            intent,
            status=submission.status,
            dry_run=submission.dry_run,
            alpaca_order_id=submission.order_id,
            raw_response={
                **submission.raw_response,
                "close_position": True,
                "position": position,
                "reason": request.reason,
            },
            source="manual_position_close",
        )
        storage.record_audit(
            "position_close_submitted" if submission.accepted else "position_close_rejected",
            submission.message,
            {
                "symbol": symbol,
                "reason": request.reason,
                "position": position,
                "intent": intent.model_dump(),
                "risk": risk_decision.model_dump(),
                "submission": submission.model_dump(),
            },
            actor="operator",
        )
        return {
            "position": position,
            "order": order,
            "risk": risk_decision.model_dump(),
            "submission": submission.model_dump(),
        }

    @app.post("/api/scheduler/run-once")
    def run_scheduler_once(request: SchedulerRunRequest) -> dict[str, object]:
        service = DryRunSchedulerService(settings, storage, app.state.strategy_params)
        return service.run_once(request)

    @app.get("/api/scheduler/runs")
    def scheduler_runs(limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[dict[str, object]]:
        return storage.list_scheduler_runs(limit=limit)

    @app.get("/api/scheduler/signals")
    def scheduler_signals(limit: Annotated[int, Query(ge=1, le=500)] = 100) -> list[dict[str, object]]:
        return storage.list_scheduler_signals(limit=limit)


    @app.get("/api/trades/active")
    def active_trades(limit: Annotated[int, Query(ge=1, le=100)] = 50) -> dict[str, object]:
        client = AlpacaClient(settings)
        try:
            open_orders = client.open_orders(limit=limit)
        except Exception as exc:  # noqa: BLE001 - keep dashboard usable during broker/API outages
            open_orders = {
                "configured": settings.alpaca_configured,
                "source": "alpaca_error",
                "orders": [],
                "message": f"Open-order lookup failed: {exc}",
            }

        local_orders = storage.list_orders(limit=limit)
        active_statuses = {
            "accepted",
            "new",
            "pending_new",
            "partially_filled",
            "dry_run_accepted",
            "submitted",
        }
        active_local_orders = [
            order for order in local_orders if str(order.get("status", "")).lower() in active_statuses
        ]
        signals = storage.list_scheduler_signals(limit=limit)
        action_signals = [signal for signal in signals if signal.get("action") in {"BUY", "SELL"}]
        active_trades = [
            {"type": "local_order", **order} for order in active_local_orders
        ] + [
            {"type": "alpaca_open_order", **order} for order in open_orders.get("orders", [])
        ]
        return {
            "source": "local_dry_run_plus_alpaca_if_configured",
            "summary": {
                "active_trades_count": len(active_trades),
                "local_orders_count": len(active_local_orders),
                "open_alpaca_orders_count": len(open_orders.get("orders", [])),
                "latest_signals_count": len(action_signals),
                "alpaca_orders_source": open_orders.get("source"),
            },
            "local_orders": active_local_orders,
            "open_alpaca_orders": open_orders,
            "latest_action_signals": action_signals[:10],
            "active_trades": active_trades[:limit],
        }

    @app.get("/api/strategy")
    def strategy() -> dict[str, object]:
        params = app.state.strategy_params
        strategy_engine = MovingAverageCrossoverStrategy(params)
        demo_signals = []
        for index, symbol in enumerate(settings.default_symbols[:20] or ("MSFT",)):
            bars = generate_synthetic_bars(symbol=symbol, seed=42 + index)
            demo_signals.append(strategy_engine.generate_signal(symbol, bars).model_dump())
        action_counts = Counter(signal["action"] for signal in demo_signals)
        return {
            "name": MovingAverageCrossoverStrategy.name,
            "description": "Stock Watchlist Adam/Eve + VWAP Adaptive Risk: handelt nur Long-Cash-Setups ohne Hebel, nutzt 5-Minuten-Signale, Adam/Eve-Flush-Recovery-Setups, Bollinger-Reclaims, Volumen-/ATR-Filter, VWAP-/Trend-/Relative-Strength-Fallbacks und reduziert den Einsatz automatisch bei hoher Volatilität oder Drawdown.",
            "params": params.__dict__,
            "latest_demo_signal": demo_signals[0] if demo_signals else None,
            "latest_demo_signals": demo_signals,
            "action_counts": dict(action_counts),
            "strategy_scope": "multi_symbol_watchlist",
        }

    @app.put("/api/strategy")
    def update_strategy(params: StrategyParamsModel) -> dict[str, object]:
        app.state.strategy_params = StrategyParams(**params.model_dump())
        storage.record_audit(
            "strategy_params_updated",
            "Strategy parameters updated.",
            params.model_dump(),
            actor="codex",
        )
        return {"params": app.state.strategy_params.__dict__}

    def _returns_for_monte_carlo_symbol(request: MonteCarloRequest, symbol: str, seed: int) -> dict[str, object]:
        fallback_reason = None
        data_source = "synthetic"
        bars = []
        if request.data_source in {"auto", "alpaca"}:
            try:
                bars = AlpacaClient(settings).historical_bars(symbol, days=request.lookback_days)
            except Exception as exc:  # noqa: BLE001 - external market-data failure should not break risk simulation
                fallback_reason = f"Alpaca historical data unavailable: {exc}"
        if bars:
            data_source = "alpaca"
        else:
            bars = generate_synthetic_bars(symbol=symbol, days=request.lookback_days, seed=seed)
            data_source = "synthetic_fallback" if request.data_source == "alpaca" else "synthetic"
            if request.data_source in {"auto", "alpaca"}:
                fallback_reason = fallback_reason or "Alpaca historical data unavailable; synthetic fallback was used."
        return {
            "symbol": symbol,
            "returns": returns_from_bars(bars),
            "data_source": data_source,
            "fallback_reason": fallback_reason,
            "bars_count": len(bars),
        }

    @app.post("/api/simulations/monte-carlo")
    def monte_carlo(request: MonteCarloRequest) -> dict[str, object]:
        requested_symbols = request.symbols or [request.symbol]
        requested_symbols = [symbol.upper() for symbol in requested_symbols][:20]
        inputs = request.model_dump(mode="json")

        if request.returns is not None and len(requested_symbols) == 1:
            summary = simulate_portfolio_paths(
                request.returns,
                initial_value=request.initial_value,
                horizon_days=request.horizon_days,
                paths=request.paths,
                seed=request.seed,
                ruin_threshold=request.ruin_threshold,
            ).model_copy(
                update={
                    "symbol": requested_symbols[0],
                    "data_source": "custom_returns",
                    "fallback_reason": None,
                    "bars_count": 0,
                }
            )
            inputs["resolved_data_source"] = "custom_returns"
            inputs["fallback_reason"] = None
            inputs["bars_count"] = 0
            metrics_payload = summary.model_dump(mode="json")
        else:
            symbol_payloads = [
                _returns_for_monte_carlo_symbol(request, symbol, request.seed + index)
                for index, symbol in enumerate(requested_symbols)
            ]
            return_series = [payload["returns"] for payload in symbol_payloads if payload["returns"]]
            min_length = min((len(series) for series in return_series), default=0)
            if min_length:
                combined_returns = [
                    sum(series[-min_length:][index] for series in return_series) / len(return_series)
                    for index in range(min_length)
                ]
            else:
                combined_returns = [0.0002]

            portfolio_summary = simulate_portfolio_paths(
                combined_returns,
                initial_value=request.initial_value,
                horizon_days=request.horizon_days,
                paths=request.paths,
                seed=request.seed,
                ruin_threshold=request.ruin_threshold,
            ).model_copy(
                update={
                    "symbol": "WATCHLIST_PORTFOLIO" if len(requested_symbols) > 1 else requested_symbols[0],
                    "data_source": "mixed" if len({payload["data_source"] for payload in symbol_payloads}) > 1 else symbol_payloads[0]["data_source"],
                    "fallback_reason": "; ".join(sorted({str(payload["fallback_reason"]) for payload in symbol_payloads if payload["fallback_reason"]})) or None,
                    "bars_count": min((int(payload["bars_count"]) for payload in symbol_payloads), default=0),
                }
            )
            per_symbol = []
            portfolio_weight = round(1 / len(requested_symbols), 6) if requested_symbols else 1.0
            portfolio_weights = [
                {"symbol": symbol, "weight": portfolio_weight}
                for symbol in requested_symbols
            ]
            for index, payload in enumerate(symbol_payloads):
                symbol_summary = simulate_portfolio_paths(
                    payload["returns"] or [0.0002],
                    initial_value=request.initial_value,
                    horizon_days=request.horizon_days,
                    paths=max(100, min(request.paths, 1000)),
                    seed=request.seed + index,
                    ruin_threshold=request.ruin_threshold,
                ).model_copy(
                    update={
                        "symbol": payload["symbol"],
                        "data_source": payload["data_source"],
                        "fallback_reason": payload["fallback_reason"],
                        "bars_count": payload["bars_count"],
                    }
                )
                symbol_payload = symbol_summary.model_dump(mode="json")
                symbol_payload["weight"] = portfolio_weight
                per_symbol.append(symbol_payload)
            metrics_payload = portfolio_summary.model_dump(mode="json")
            metrics_payload["portfolio_mode"] = "equal_weight_watchlist" if len(requested_symbols) > 1 else "single_symbol"
            metrics_payload["symbols"] = requested_symbols
            metrics_payload["portfolio_weights"] = portfolio_weights
            metrics_payload["per_symbol"] = per_symbol
            inputs["resolved_data_source"] = metrics_payload["data_source"]
            inputs["fallback_reason"] = metrics_payload["fallback_reason"]
            inputs["bars_count"] = metrics_payload["bars_count"]
            inputs["portfolio_mode"] = metrics_payload["portfolio_mode"]
            inputs["portfolio_weights"] = portfolio_weights

        record = storage.record_simulation(
            "monte_carlo",
            request.seed,
            inputs,
            metrics_payload,
        )
        storage.record_audit(
            "simulation_completed",
            "Monte Carlo simulation completed.",
            {"simulation_id": record["id"], "metrics": metrics_payload, "data_source": metrics_payload.get("data_source")},
            actor="codex",
        )
        return {"simulation": record, "summary": metrics_payload}

    @app.get("/api/simulations/latest")
    def latest_simulations(limit: Annotated[int, Query(ge=1, le=100)] = 5) -> list[dict[str, object]]:
        return storage.list_simulations(limit=limit)

    def _bars_for_backtest_symbol(request: BacktestRequest, symbol: str, seed: int) -> dict[str, object]:
        fallback_reason = None
        data_source = "synthetic"
        bars = []
        if request.data_source in {"auto", "alpaca"}:
            try:
                bars = AlpacaClient(settings).historical_bars(symbol, days=request.days, timeframe=request.timeframe)
            except Exception as exc:  # noqa: BLE001 - external market-data failure should not break research mode
                fallback_reason = f"Alpaca historical data unavailable: {exc}"
        if bars:
            data_source = "alpaca"
        else:
            bars = generate_synthetic_bars(symbol=symbol, days=request.days, seed=seed)
            data_source = "synthetic_fallback" if request.data_source == "alpaca" else "synthetic"
            if request.data_source in {"auto", "alpaca"}:
                fallback_reason = fallback_reason or "Alpaca historical data unavailable; synthetic fallback was used."
        return {
            "symbol": symbol,
            "bars": bars,
            "data_source": data_source,
            "fallback_reason": fallback_reason,
            "bars_count": len(bars),
        }

    @app.post("/api/backtests/run")
    def run_backtest_endpoint(request: BacktestRequest) -> dict[str, object]:
        params = (
            StrategyParams(**request.strategy.model_dump())
            if request.strategy is not None
            else app.state.strategy_params
        )
        requested_symbols = request.symbols or [request.symbol]
        requested_symbols = [symbol.upper() for symbol in requested_symbols][:20]
        symbol_payloads = [
            _bars_for_backtest_symbol(request, symbol, request.seed + index)
            for index, symbol in enumerate(requested_symbols)
        ]
        bars_by_symbol = {str(payload["symbol"]): payload["bars"] for payload in symbol_payloads}
        data_sources = {str(payload["data_source"]) for payload in symbol_payloads}
        data_source = "mixed" if len(data_sources) > 1 else next(iter(data_sources), "synthetic")
        fallback_reason = "; ".join(
            sorted({str(payload["fallback_reason"]) for payload in symbol_payloads if payload["fallback_reason"]})
        ) or None
        bars_count = min((int(payload["bars_count"]) for payload in symbol_payloads), default=0)

        inputs = request.model_dump(mode="json")
        inputs["symbols"] = requested_symbols
        inputs["portfolio_mode"] = "multi_symbol_watchlist" if len(requested_symbols) > 1 else "single_symbol"
        inputs["resolved_data_source"] = data_source
        inputs["fallback_reason"] = fallback_reason
        inputs["bars_count"] = bars_count
        inputs["bars_per_symbol"] = {str(payload["symbol"]): int(payload["bars_count"]) for payload in symbol_payloads}
        inputs["timeframe"] = request.timeframe
        inputs["per_symbol"] = [
            {
                "symbol": payload["symbol"],
                "data_source": payload["data_source"],
                "fallback_reason": payload["fallback_reason"],
                "bars_count": payload["bars_count"],
            }
            for payload in symbol_payloads
        ]

        if len(requested_symbols) > 1:
            result = run_portfolio_backtest(
                bars_by_symbol,
                params,
                initial_cash=request.initial_cash,
                trade_notional=request.trade_notional,
            )
        else:
            result = run_backtest(
                bars_by_symbol[requested_symbols[0]],
                params,
                initial_cash=request.initial_cash,
                trade_notional=request.trade_notional,
            )

        result_payload = result.model_dump(mode="json")
        result_payload["symbols"] = requested_symbols
        result_payload["portfolio_mode"] = inputs["portfolio_mode"]
        result_payload["per_symbol"] = inputs["per_symbol"]
        trade_symbols = sorted({trade.symbol for trade in result.trades})
        result_payload["trade_symbols"] = trade_symbols
        result_payload["trade_symbol_counts"] = dict(Counter(trade.symbol for trade in result.trades))
        metrics_payload = result.metrics.model_dump(mode="json")
        metrics_payload["symbols_count"] = len(requested_symbols)
        metrics_payload["trade_symbols_count"] = len(trade_symbols)

        record = storage.record_backtest(
            result.strategy_name,
            result.symbol,
            inputs,
            metrics_payload,
            [trade.model_dump(mode="json") for trade in result.trades],
            [point.model_dump(mode="json") for point in result.equity_curve],
        )
        storage.record_audit(
            "backtest_completed",
            "Portfolio backtest completed." if len(requested_symbols) > 1 else "Backtest completed.",
            {"backtest_id": record["id"], "metrics": metrics_payload, "data_source": data_source, "symbols": requested_symbols},
            actor="codex",
        )
        return {
            "backtest": record,
            "result": result_payload,
            "data_source": data_source,
            "fallback_reason": fallback_reason,
            "bars_count": bars_count,
        }

    @app.get("/api/backtests/latest")
    def latest_backtests(limit: Annotated[int, Query(ge=1, le=100)] = 5) -> list[dict[str, object]]:
        return storage.list_backtests(limit=limit)

    @app.post("/api/improvement/run")
    def run_improvement(request: ImprovementRequest) -> dict[str, object]:
        bars = generate_synthetic_bars(symbol=request.symbol, days=request.days, seed=request.seed)
        improver = RecursiveImprover(settings)
        result = improver.improve(app.state.strategy_params, bars, seed=request.seed)
        if result["promoted"]:
            app.state.strategy_params = StrategyParams(**result["selected_params"])
        storage.record_audit(
            "strategy_improvement_completed",
            "Recursive improvement loop completed.",
            result,
            actor="hermes",
        )
        return result

    @app.get("/api/audit-events")
    def audit_events(limit: Annotated[int, Query(ge=1, le=500)] = 100) -> list[dict[str, object]]:
        return storage.list_audit_events(limit=limit)

    @app.get("/api/alerts")
    def alerts(limit: Annotated[int, Query(ge=1, le=100)] = 50) -> list[dict[str, object]]:
        return build_alerts(storage, settings, limit=limit)

    @app.get("/api/reports/daily")
    def daily_report(report_date: Annotated[str | None, Query(alias="date")] = None) -> dict[str, object]:
        selected_date = report_date or datetime.now(UTC).date().isoformat()

        def from_selected_day(record: dict[str, object]) -> bool:
            return str(record.get("created_at", "")).startswith(selected_date)

        orders = [order for order in storage.list_orders(limit=500) if from_selected_day(order)]
        backtests = [backtest for backtest in storage.list_backtests(limit=500) if from_selected_day(backtest)]
        simulations = [simulation for simulation in storage.list_simulations(limit=500) if from_selected_day(simulation)]
        audit_events = [event for event in storage.list_audit_events(limit=500) if from_selected_day(event)]
        alerts = [alert for alert in build_alerts(storage, settings, limit=100) if from_selected_day(alert)]
        order_statuses = Counter(str(order["status"]) for order in orders)
        audit_event_types = Counter(str(event["event_type"]) for event in audit_events)
        return {
            "date": selected_date,
            "portfolio": AlpacaClient(settings).portfolio_status(settings.default_symbols),
            "orders": {
                "count": len(orders),
                "dry_run_count": sum(1 for order in orders if order["dry_run"]),
                "statuses": dict(order_statuses),
                "latest": orders[:5],
            },
            "backtests": {
                "count": len(backtests),
                "latest": backtests[:3],
            },
            "simulations": {
                "count": len(simulations),
                "latest": simulations[:3],
            },
            "audit_events": {
                "count": len(audit_events),
                "event_types": dict(audit_event_types),
                "latest": audit_events[:10],
            },
            "alerts": {
                "count": len(alerts),
                "critical_count": sum(1 for alert in alerts if alert["severity"] == "critical"),
                "latest": alerts[:10],
            },
            "safety": {
                "dry_run": settings.dry_run,
                "paper_trading_only": settings.paper_trading_only,
            },
        }

    return app


app = create_app()
