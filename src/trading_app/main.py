from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from trading_app.alpaca import AlpacaClient
from trading_app.auth import AuthService, auth_state
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
PUBLIC_AUTH_PATHS = {"/health", "/login", "/logout"}


def add_security_headers(response: Response) -> Response:
    response.headers["X-Trading-Disclaimer"] = "Research and paper trading only; not financial advice."
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


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

    return app


app = create_app()
