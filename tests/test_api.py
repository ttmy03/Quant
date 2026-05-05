from trading_app.config import Settings
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
            json={"seed": 7, "paths": 200, "horizon_days": 60, "initial_value": 10_000},
        )

    assert response.status_code == 200
    summary = response.json()["summary"]
    fan_chart = summary["fan_chart"]
    histogram = summary["terminal_value_histogram"]

    assert len(fan_chart) == 61
    assert fan_chart[0] == {"day": 0, "p05": 10000.0, "p50": 10000.0, "p95": 10000.0}
    assert fan_chart[-1]["day"] == 60
    assert fan_chart[-1]["p05"] <= fan_chart[-1]["p50"] <= fan_chart[-1]["p95"]
    assert len(histogram) == 20
    assert sum(bucket["count"] for bucket in histogram) == 200


def test_dashboard_includes_visual_chart_canvases(tmp_path) -> None:
    settings = Settings(DATABASE_PATH=tmp_path / "test.sqlite3", AUTH_ENABLED=False, _env_file=None)
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="monte-carlo-fan-chart"' in response.text
    assert 'id="monte-carlo-histogram"' in response.text
    assert 'id="backtest-equity-chart"' in response.text
    assert 'id="trading-control-card"' in response.text
    assert 'id="enable-kill-switch"' in response.text
    assert 'id="run-scheduler-once"' in response.text
    assert 'id="positions-table"' in response.text
    assert 'id="balance-metrics"' in response.text
    assert 'id="active-trade-metrics"' in response.text
    assert 'id="active-trades"' in response.text
    assert 'class="status-list muted trade-scroll"' in response.text
    assert 'id="portfolio-live-status"' in response.text
    assert 'U/PnL %' in response.text
    assert "data-close-position" in response.text
    assert "close-position-button" in response.text
    assert "/api/positions/${encodeURIComponent(symbol)}/close" in response.text
    assert "Schließt diese einzelne Position manuell" in response.text
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
