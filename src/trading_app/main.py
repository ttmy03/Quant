from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from trading_app.alpaca import AlpacaClient
from trading_app.config import Settings, get_settings
from trading_app.data import generate_synthetic_bars, returns_from_bars
from trading_app.improver import RecursiveImprover
from trading_app.monte_carlo import simulate_portfolio_paths
from trading_app.risk import RiskGuard
from trading_app.schemas import (
    ImprovementRequest,
    MonteCarloRequest,
    OrderIntent,
    StrategyParamsModel,
)
from trading_app.storage import Storage
from trading_app.strategy import MovingAverageCrossoverStrategy, StrategyParams


STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None, storage: Storage | None = None) -> FastAPI:
    settings = settings or get_settings()
    storage = storage or Storage(settings.database_path)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Paper-first automated stock trading research app. Not financial advice.",
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.state.settings = settings
    app.state.storage = storage
    app.state.strategy_params = StrategyParams()

    @app.get("/")
    def dashboard() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

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

    @app.get("/api/portfolio/status")
    def portfolio_status() -> dict[str, object]:
        client = AlpacaClient(settings)
        account = client.account_status()
        bars = client.latest_bars(settings.default_symbols)
        return {
            "account": account,
            "latest_bars": [bar.model_dump(mode="json") for bar in bars],
            "disclaimer": "Research and paper trading only. Not financial advice.",
        }

    @app.get("/api/orders")
    def orders(limit: Annotated[int, Query(ge=1, le=500)] = 100) -> list[dict[str, object]]:
        return storage.list_orders(limit=limit)

    @app.post("/api/orders")
    def submit_order(intent: OrderIntent) -> dict[str, object]:
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

    @app.get("/api/strategy")
    def strategy() -> dict[str, object]:
        params = app.state.strategy_params
        bars = generate_synthetic_bars(settings.default_symbols[0] if settings.default_symbols else "AAPL")
        signal = MovingAverageCrossoverStrategy(params).generate_signal(bars[-1].symbol, bars)
        return {
            "name": MovingAverageCrossoverStrategy.name,
            "params": params.__dict__,
            "latest_demo_signal": signal.model_dump(),
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

    @app.post("/api/simulations/monte-carlo")
    def monte_carlo(request: MonteCarloRequest) -> dict[str, object]:
        returns = request.returns
        if returns is None:
            bars = generate_synthetic_bars(days=180, seed=request.seed)
            returns = returns_from_bars(bars)
        summary = simulate_portfolio_paths(
            returns,
            initial_value=request.initial_value,
            horizon_days=request.horizon_days,
            paths=request.paths,
            seed=request.seed,
            ruin_threshold=request.ruin_threshold,
        )
        record = storage.record_simulation(
            "monte_carlo",
            request.seed,
            request.model_dump(),
            summary.model_dump(),
        )
        storage.record_audit(
            "simulation_completed",
            "Monte Carlo simulation completed.",
            {"simulation_id": record["id"], "metrics": summary.model_dump()},
            actor="codex",
        )
        return {"simulation": record, "summary": summary.model_dump()}

    @app.get("/api/simulations/latest")
    def latest_simulations(limit: Annotated[int, Query(ge=1, le=100)] = 5) -> list[dict[str, object]]:
        return storage.list_simulations(limit=limit)

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

    @app.middleware("http")
    async def add_disclaimer_header(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Trading-Disclaimer"] = "Research and paper trading only; not financial advice."
        return response

    return app


app = create_app()
