import time

from trading_app.config import Settings
from trading_app.data import generate_synthetic_bars
from trading_app.main import create_app
from trading_app.storage import Storage
from tests.asgi_client import ASGITestClient


def test_health_endpoint(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=True,
        ADMIN_PASSWORD="test-password",
        SESSION_SECRET="test-session-secret",
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["dry_run"] is True


def test_dashboard_redirects_to_login_when_auth_enabled(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=True,
        ADMIN_PASSWORD="test-password",
        SESSION_SECRET="test-session-secret",
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_allows_dashboard_and_api_access(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=True,
        ADMIN_PASSWORD="test-password",
        SESSION_SECRET="test-session-secret",
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        login_response = client.post(
            "/login",
            data={"username": "admin", "password": "test-password"},
            follow_redirects=False,
        )
        dashboard_response = client.get("/")
        config_response = client.get("/api/config")
        me_response = client.get("/api/auth/me")

    assert login_response.status_code == 303
    assert login_response.headers["location"] == "/"
    assert "paper_quant_session=" in login_response.headers["set-cookie"]
    assert "HttpOnly" in login_response.headers["set-cookie"]
    assert "SameSite=lax" in login_response.headers["set-cookie"]
    assert dashboard_response.status_code == 200
    assert "Paper Quant Dashboard" in dashboard_response.text
    assert config_response.status_code == 200
    assert config_response.json()["auth_enabled"] is True
    assert me_response.status_code == 200
    assert me_response.json()["authenticated"] is True
    assert me_response.json()["user"]["username"] == "admin"
    assert me_response.json()["safety"]["dry_run"] is True


def test_bad_login_is_rejected(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=True,
        ADMIN_PASSWORD="test-password",
        SESSION_SECRET="test-session-secret",
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        login_response = client.post(
            "/login",
            data={"username": "admin", "password": "wrong-password"},
        )
        config_response = client.get("/api/config")

    assert login_response.status_code == 401
    assert "paper_quant_session=" not in login_response.headers.get("set-cookie", "")
    assert config_response.status_code == 401


def test_auth_can_be_disabled_for_dev_and_tests(tmp_path) -> None:
    settings = Settings(DATABASE_PATH=tmp_path / "test.sqlite3", AUTH_ENABLED=False, _env_file=None)
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        dashboard_response = client.get("/")
        config_response = client.get("/api/config")
        me_response = client.get("/api/auth/me")

    assert dashboard_response.status_code == 200
    assert config_response.status_code == 200
    assert config_response.json()["auth_enabled"] is False
    assert me_response.status_code == 200
    assert me_response.json()["authenticated"] is True
    assert me_response.json()["user"] is None


def test_order_endpoint_records_dry_run_order(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        DEFAULT_SYMBOLS="AAPL",
        AUTH_ENABLED=False,
        ALPACA_API_KEY="",
        ALPACA_SECRET_KEY="",
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        response = client.post("/api/orders", json={"symbol": "AAPL", "side": "buy", "qty": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["submission"]["status"] == "dry_run_accepted"
    assert payload["order"]["dry_run"] is True


def test_backtest_endpoint_runs_and_persists_when_auth_disabled(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        DEFAULT_SYMBOLS="AAPL",
        AUTH_ENABLED=False,
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        response = client.post(
            "/api/backtests/run",
            json={
                "symbol": "AAPL",
                "days": 80,
                "seed": 42,
                "initial_cash": 10_000,
                "trade_notional": 1_000,
                "strategy": {"short_window": 3, "long_window": 8, "min_crossover_pct": 0.0},
            },
        )
        latest_response = client.get("/api/backtests/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["symbol"] == "AAPL"
    assert payload["result"]["metrics"]["final_equity"] > 0
    assert "id" in payload["backtest"]
    assert latest_response.status_code == 200
    assert latest_response.json()[0]["symbol"] == "AAPL"
    assert payload["data_source"] == "synthetic"
    assert payload["bars_count"] == 80
    assert payload["backtest"]["inputs"]["timeframe"] == "5Min"
    assert payload["backtest"]["inputs"]["bars_per_symbol"]["AAPL"] == 80
    assert "profit_factor" in payload["backtest"]["metrics"]


def test_backtest_endpoint_can_run_watchlist_portfolio(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=False,
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        response = client.post(
            "/api/backtests/run",
            json={
                "symbols": ["ALGM", "AMKR", "TREX"],
                "days": 80,
                "seed": 42,
                "initial_cash": 10_000,
                "trade_notional": 1_000,
                "data_source": "synthetic",
                "strategy": {"short_window": 3, "long_window": 8, "min_crossover_pct": 0.0},
            },
        )
        latest_response = client.get("/api/backtests/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["symbol"] == "WATCHLIST_PORTFOLIO"
    assert payload["result"]["portfolio_mode"] == "multi_symbol_watchlist"
    assert payload["backtest"]["inputs"]["symbols"] == ["ALGM", "AMKR", "TREX"]
    assert payload["backtest"]["inputs"]["portfolio_mode"] == "multi_symbol_watchlist"
    assert payload["backtest"]["metrics"]["symbols_count"] == 3
    assert payload["backtest"]["metrics"]["trades_count"] == len(payload["backtest"]["trades"])
    assert {trade["symbol"] for trade in payload["backtest"]["trades"]}.issubset({"ALGM", "AMKR", "TREX"})
    assert len(payload["backtest"]["equity_curve"]) == 80
    assert latest_response.json()[0]["symbol"] == "WATCHLIST_PORTFOLIO"


def test_backtest_endpoint_reports_alpaca_fallback_when_requested_without_credentials(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        DEFAULT_SYMBOLS="AAPL",
        AUTH_ENABLED=False,
        ALPACA_API_KEY="",
        ALPACA_SECRET_KEY="",
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        response = client.post(
            "/api/backtests/run",
            json={"symbol": "AAPL", "days": 60, "seed": 42, "data_source": "alpaca"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_source"] == "synthetic_fallback"
    assert payload["fallback_reason"] == "Alpaca historical data unavailable; synthetic fallback was used."
    assert payload["backtest"]["inputs"]["data_source"] == "alpaca"
    assert payload["backtest"]["inputs"]["resolved_data_source"] == "synthetic_fallback"


def test_backtest_endpoint_fetches_external_watchlist_symbols_concurrently(tmp_path, monkeypatch) -> None:
    class SlowEmptyAlpacaClient:
        def __init__(self, settings):
            self.settings = settings

        def historical_bars(self, symbol: str, *, days: int, timeframe: str = "1Day"):
            time.sleep(0.05)
            return []

    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=False,
        ALPACA_API_KEY="key",
        ALPACA_SECRET_KEY="secret",
        _env_file=None,
    )
    monkeypatch.setattr("trading_app.main.AlpacaClient", SlowEmptyAlpacaClient)
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    start = time.perf_counter()
    with ASGITestClient(app) as client:
        response = client.post(
            "/api/backtests/run",
            json={
                "symbols": ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"],
                "days": 40,
                "seed": 42,
                "data_source": "alpaca",
            },
        )
    elapsed = time.perf_counter() - start

    assert response.status_code == 200
    assert elapsed < 0.20
    assert response.json()["backtest"]["metrics"]["symbols_count"] == 6
    assert response.json()["data_source"] == "synthetic_fallback"


def test_backtest_endpoint_caps_large_intraday_alpaca_payloads(tmp_path, monkeypatch) -> None:
    class BigIntradayAlpacaClient:
        def __init__(self, settings):
            self.settings = settings

        def historical_bars(self, symbol: str, *, days: int, timeframe: str = "1Day"):
            assert timeframe == "5Min"
            return generate_synthetic_bars(symbol=symbol, days=1_000, seed=sum(ord(char) for char in symbol))

    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=False,
        ALPACA_API_KEY="key",
        ALPACA_SECRET_KEY="secret",
        _env_file=None,
    )
    monkeypatch.setattr("trading_app.main.AlpacaClient", BigIntradayAlpacaClient)
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        response = client.post(
            "/api/backtests/run",
            json={
                "symbols": ["AAA", "BBB", "CCC"],
                "days": 40,
                "seed": 42,
                "data_source": "alpaca",
                "timeframe": "5Min",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_source"] == "alpaca"
    assert payload["bars_count"] == 40
    assert payload["backtest"]["inputs"]["bars_per_symbol"] == {"AAA": 40, "BBB": 40, "CCC": 40}
    assert len(payload["backtest"]["equity_curve"]) == 40

def test_monte_carlo_endpoint_returns_visualization_series(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        DEFAULT_SYMBOLS="AAPL",
        AUTH_ENABLED=False,
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        response = client.post(
            "/api/simulations/monte-carlo",
            json={"symbol": "AMKR", "seed": 7, "paths": 200, "horizon_days": 60, "lookback_days": 80, "initial_value": 10_000, "data_source": "synthetic"},
        )

    assert response.status_code == 200
    summary = response.json()["summary"]
    fan_chart = summary["fan_chart"]
    histogram = summary["terminal_value_histogram"]

    assert len(fan_chart) == 61
    assert summary["symbol"] == "AMKR"
    assert summary["data_source"] == "synthetic"
    assert summary["bars_count"] == 80
    assert response.json()["simulation"]["inputs"]["symbol"] == "AMKR"
    assert response.json()["simulation"]["inputs"]["resolved_data_source"] == "synthetic"
    assert fan_chart[0] == {"day": 0, "p05": 10000.0, "p50": 10000.0, "p95": 10000.0}
    assert fan_chart[-1]["day"] == 60
    assert fan_chart[-1]["p05"] <= fan_chart[-1]["p50"] <= fan_chart[-1]["p95"]
    assert len(histogram) == 20
    assert sum(bucket["count"] for bucket in histogram) == 200


def test_monte_carlo_can_simulate_all_watchlist_symbols_together(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=False,
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        response = client.post(
            "/api/simulations/monte-carlo",
            json={
                "symbols": ["ALGM", "AMKR", "TREX"],
                "seed": 11,
                "paths": 120,
                "horizon_days": 30,
                "lookback_days": 80,
                "initial_value": 10_000,
                "data_source": "synthetic",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    summary = payload["summary"]
    assert summary["symbol"] == "WATCHLIST_PORTFOLIO"
    assert summary["portfolio_mode"] == "equal_weight_watchlist"
    assert summary["symbols"] == ["ALGM", "AMKR", "TREX"]
    assert len(summary["per_symbol"]) == 3
    assert {item["symbol"] for item in summary["per_symbol"]} == {"ALGM", "AMKR", "TREX"}
    assert summary["portfolio_weights"] == [
        {"symbol": "ALGM", "weight": 0.333333},
        {"symbol": "AMKR", "weight": 0.333333},
        {"symbol": "TREX", "weight": 0.333333},
    ]
    assert all(item["weight"] == 0.333333 for item in summary["per_symbol"])
    assert len(summary["fan_chart"]) == 31
    assert payload["simulation"]["inputs"]["portfolio_mode"] == "equal_weight_watchlist"
    assert payload["simulation"]["inputs"]["portfolio_weights"] == summary["portfolio_weights"]



def test_watchlist_endpoint_returns_dynamic_halal_msci_world_large_cap_candidates(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=False,
        ALPACA_API_KEY="",
        ALPACA_SECRET_KEY="",
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        response = client.get("/api/watchlist")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 250
    assert len(payload["symbols"]) == 250
    assert 200 <= payload["universe_count"] <= 300
    assert len(payload["universe_symbols"]) == payload["universe_count"]
    assert payload["eligible_symbols"] == payload["symbols"]
    assert payload["methodology"]["universe"] == "279 qualitatively screened MSCI World-style halal large-cap research candidates; default watchlist returns top 250"
    assert payload["methodology"]["index_reference"] == "MSCI World developed-market large caps / MSCI Islamic-style sector screen"
    assert payload["candidates"][0]["rank"] == 1
    assert all(candidate["halal_screen"] == "candidate_only_qualitative_pass" for candidate in payload["candidates"])
    assert all(candidate["market_cap_category"] == "largecap" for candidate in payload["candidates"])
    assert all(candidate["undervalued"] is True for candidate in payload["candidates"])
    assert all(candidate["margin_of_safety"] > 0 for candidate in payload["candidates"])
    assert {"Technology", "Healthcare", "Industrials", "Materials", "Consumer", "Consumer Staples"}.issubset({candidate["sector"] for candidate in payload["candidates"]})
    assert {"MSFT", "NVDA", "ASML", "LLY", "NVO", "LIN", "CAT", "TM"}.issubset(set(payload["symbols"]))
    assert payload["symbols"] == [candidate["symbol"] for candidate in payload["candidates"]]

def test_dashboard_includes_visual_chart_canvases(tmp_path) -> None:
    settings = Settings(DATABASE_PATH=tmp_path / "test.sqlite3", AUTH_ENABLED=False, _env_file=None)
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="monte-carlo-fan-chart"' in response.text
    assert 'id="monte-carlo-line-legend"' in response.text
    assert 'id="monte-carlo-histogram"' in response.text
    assert 'id="backtest-equity-chart"' in response.text
    assert 'id="backtest-days"' in response.text
    assert 'id="backtest-timeframe"' in response.text
    assert "Backtest Zeitraum" in response.text
    assert "Backtest Timeframe" in response.text
    assert "1Day ist kein Intraday-Backtest" in response.text
    assert "Profit Factor" in response.text
    assert "Anfangswert" in response.text
    assert "Endwert" in response.text
    assert 'id="trading-control-card"' in response.text
    assert 'id="enable-kill-switch"' in response.text
    assert 'id="run-scheduler-once"' in response.text
    assert 'id="positions-table"' in response.text
    assert 'id="balance-metrics"' in response.text
    assert 'id="active-trade-metrics"' in response.text
    assert 'id="active-trades"' in response.text
    assert 'id="watchlist-card"' in response.text
    assert 'id="watchlist-table"' in response.text
    assert 'id="refresh-watchlist"' in response.text
    assert "Dynamische Halal Large-Cap Watchlist" in response.text
    assert "MSCI World" in response.text
    assert "250 ausgewählte" in response.text
    assert 'api("/api/watchlist")' in response.text
    assert "renderWatchlist" in response.text
    assert "primaryWatchlistSymbol" in response.text
    assert "pickLatestWatchlistBacktest" in response.text
    assert "pickLatestWatchlistSimulation" in response.text
    assert "latestAnalysisSymbols" in response.text
    assert "latestWatchlistSymbols.length ? latestWatchlistSymbols : latestUniverseSymbols" in response.text
    assert "gerankte Watchlist-Symbole" in response.text
    assert "Top 20 Analyse" in response.text
    assert "universe_symbols" in response.text
    assert "Backtest ID" in response.text
    assert "Berechnet" in response.text
    assert "renderBacktest(pickLatestWatchlistBacktest(backtests))" in response.text
    assert "renderMonteCarlo(pickLatestWatchlistSimulation(simulations)?.metrics)" in response.text
    assert "renderBacktest(backtests[0])" not in response.text
    assert "renderMonteCarlo(simulations[0]?.metrics)" not in response.text
    assert 'body: json({ symbols: latestAnalysisSymbols().slice(0, 20), seed: 42, paths: 1000, horizon_days: 252, lookback_days: 252, data_source: "auto" })' in response.text
    assert 'body: json({ symbols: latestAnalysisSymbols().slice(0, 20), days, seed: 42, initial_cash: 10000, trade_notional: 1000, data_source: dataSource, timeframe })' in response.text
    assert "await refresh();\n          renderBacktest(result.backtest);" in response.text
    assert "Gleichbleibende Equity wird als horizontale Linie angezeigt" in response.text
    assert "Gesamtportfolio Equity" in response.text
    assert "Gekauft/verkauft" in response.text
    assert "Watchlist Portfolio" in response.text
    assert "perSymbol" in response.text
    assert "renderMonteCarloLineLegend" in response.text
    assert "Gewichtung" in response.text
    assert "Portfolio-Linien im Graph" in response.text
    assert 'id="simulation-metrics"' in response.text
    assert "Datenquelle" in response.text
    assert 'class="status-list muted trade-scroll"' in response.text
    assert 'id="portfolio-live-status"' in response.text
    assert 'U/PnL %' in response.text
    assert "data-close-position" in response.text
    assert "close-position-button" in response.text
    assert "/api/positions/${encodeURIComponent(symbol)}/close" in response.text
    assert "Schließt diese einzelne Position manuell" in response.text
    assert "Intraday Long-only Strategie" in response.text
    assert "kein Hebel" in response.text
    assert "Basis-Risiko" in response.text
    assert "Risiko-Korridor" in response.text
    assert "strategy.params?.intraday_timeframe" in response.text
    assert "signal.risk_fraction" in response.text
    assert "signedPct" in response.text
    assert "pnlClass" in response.text
    assert "refreshLivePortfolio" in response.text
    assert "setInterval" in response.text
    assert 'api("/api/trades/active")' in response.text
    assert "Balance / Kontostand" in response.text
    assert "Aktuelle Trades & laufende Orders" in response.text
    assert 'id="daily-report"' in response.text
    assert 'id="alerts"' in response.text
    assert 'id="quick-start"' in response.text
    assert 'id="safety-section"' in response.text
    assert 'id="portfolio-section"' in response.text
    assert 'id="analysis-section"' in response.text
    assert 'id="actions-section"' in response.text
    assert 'id="history-section"' in response.text
    assert "Schritt 1" in response.text
    assert "Sicherheit & Freigabe" in response.text
    assert "Portfolio Überblick" in response.text
    assert "Dry-Run Aktionen" in response.text
    assert "Not-Aus aktivieren" in response.text
    assert 'id="process-status"' in response.text
    assert 'data-help="Aktiviert den Kill-Switch' in response.text
    assert 'data-help="Startet eine Monte-Carlo-Simulation' in response.text
    assert 'data-help="Sendet eine manuelle Testorder' in response.text
    assert "button-help-dot" in response.text
    assert "withButtonLoading" in response.text
    assert "is-loading" in response.text
    assert "läuft gerade" in response.text
    assert "<pre" not in response.text
    assert "renderStatusList" in response.text
    assert "renderDetailGrid" in response.text
    assert "/api/trading-control/kill-switch" in response.text
    assert "/api/scheduler/run-once" in response.text
    assert "/api/alerts" in response.text
    assert "/api/reports/daily" in response.text
    assert "renderLineChart" in response.text
    assert "renderHistogram" in response.text
