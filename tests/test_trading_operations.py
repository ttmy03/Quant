from __future__ import annotations

from datetime import UTC, datetime

from trading_app.config import Settings
from trading_app.main import create_app
from trading_app.schemas import OrderIntent, OrderSubmission
from trading_app.storage import Storage
from tests.asgi_client import ASGITestClient


def test_trading_control_state_persists_and_audits_changes(tmp_path) -> None:
    database_path = tmp_path / "test.sqlite3"
    settings = Settings(DATABASE_PATH=database_path, AUTH_ENABLED=False, _env_file=None)
    storage = Storage(database_path)
    app = create_app(settings=settings, storage=storage)

    with ASGITestClient(app) as client:
        initial = client.get("/api/trading-control")
        kill_response = client.post(
            "/api/trading-control/kill-switch",
            json={"enabled": True, "reason": "operator test"},
        )
        pause_response = client.post("/api/trading-control/pause", json={"reason": "market closed"})
        audit_response = client.get("/api/audit-events")

    assert initial.status_code == 200
    assert initial.json()["can_trade"] is True
    assert kill_response.status_code == 200
    assert kill_response.json()["kill_switch_active"] is True
    assert kill_response.json()["can_trade"] is False
    assert pause_response.status_code == 200
    assert pause_response.json()["paused"] is True
    event_types = [event["event_type"] for event in audit_response.json()]
    assert "kill_switch_enabled" in event_types
    assert "trading_paused" in event_types

    reloaded_app = create_app(settings=settings, storage=Storage(database_path))
    with ASGITestClient(reloaded_app) as client:
        reloaded = client.get("/api/trading-control")

    assert reloaded.status_code == 200
    assert reloaded.json()["kill_switch_active"] is True
    assert reloaded.json()["paused"] is True
    assert reloaded.json()["can_trade"] is False


def test_resume_clears_pause_but_not_active_kill_switch(tmp_path) -> None:
    settings = Settings(DATABASE_PATH=tmp_path / "test.sqlite3", AUTH_ENABLED=False, _env_file=None)
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        client.post("/api/trading-control/kill-switch", json={"enabled": True, "reason": "incident"})
        client.post("/api/trading-control/pause", json={"reason": "operator pause"})
        resume_response = client.post("/api/trading-control/resume", json={"reason": "operator resume"})
        audit_response = client.get("/api/audit-events")

    assert resume_response.status_code == 200
    payload = resume_response.json()
    assert payload["paused"] is False
    assert payload["kill_switch_active"] is True
    assert payload["can_trade"] is False
    assert audit_response.json()[0]["event_type"] == "trading_resumed"


def test_active_kill_switch_blocks_manual_orders_without_live_submission(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=False,
        DEFAULT_SYMBOLS="AAPL",
        ALPACA_API_KEY="",
        ALPACA_SECRET_KEY="",
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        client.post("/api/trading-control/kill-switch", json={"enabled": True, "reason": "operator test"})
        order_response = client.post("/api/orders", json={"symbol": "AAPL", "side": "buy", "qty": 1})
        orders_response = client.get("/api/orders")
        audit_response = client.get("/api/audit-events")

    assert order_response.status_code == 200
    assert order_response.json()["submission"]["status"] == "blocked_by_control"
    assert order_response.json()["submission"]["dry_run"] is True
    assert orders_response.json() == []
    assert audit_response.json()[0]["event_type"] == "order_blocked_by_control"


def test_on_demand_scheduler_records_dry_run_cycle_signals_and_orders(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=False,
        DEFAULT_SYMBOLS="AAPL",
        ALPACA_API_KEY="",
        ALPACA_SECRET_KEY="",
        DRY_RUN=True,
        PAPER_TRADING_ONLY=True,
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        response = client.post("/api/scheduler/run-once", json={"symbols": ["AAPL"], "seed": 1})
        runs_response = client.get("/api/scheduler/runs")
        signals_response = client.get("/api/scheduler/signals")
        orders_response = client.get("/api/orders")
        audit_response = client.get("/api/audit-events")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["status"] == "completed"
    assert payload["run"]["dry_run"] is True
    assert payload["run"]["paper_trading_only"] is True
    assert payload["no_live_orders_sent"] is True
    assert payload["signals"][0]["symbol"] == "AAPL"
    assert payload["signals"][0]["action"] in {"BUY", "SELL", "HOLD"}
    assert runs_response.json()[0]["id"] == payload["run"]["id"]
    assert signals_response.json()[0]["scheduler_run_id"] == payload["run"]["id"]
    assert all(order["dry_run"] is True for order in orders_response.json())
    if payload["orders"]:
        assert orders_response.json()[0]["source"] == "scheduler"
        assert orders_response.json()[0]["scheduler_run_id"] == payload["run"]["id"]
    assert audit_response.json()[0]["event_type"] == "scheduler_run_completed"


def test_scheduler_respects_trading_control_blocks(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=False,
        DEFAULT_SYMBOLS="AAPL",
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        client.post("/api/trading-control/pause", json={"reason": "operator pause"})
        response = client.post("/api/scheduler/run-once", json={"symbols": ["AAPL"], "seed": 1})
        orders_response = client.get("/api/orders")

    assert response.status_code == 200
    assert response.json()["run"]["status"] == "blocked_by_control"
    assert response.json()["signals"] == []
    assert response.json()["orders"] == []
    assert orders_response.json() == []


def test_alerts_derive_operator_warnings_from_control_and_audit_events(tmp_path) -> None:
    settings = Settings(DATABASE_PATH=tmp_path / "test.sqlite3", AUTH_ENABLED=False, _env_file=None)
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        client.post("/api/trading-control/kill-switch", json={"enabled": True, "reason": "operator test"})
        client.post("/api/orders", json={"symbol": "AAPL", "side": "buy", "qty": 1})
        response = client.get("/api/alerts")

    assert response.status_code == 200
    alerts = response.json()
    assert alerts[0]["severity"] == "critical"
    assert alerts[0]["title"] == "Kill-Switch aktiv"
    assert any(alert["source"] == "audit_events" for alert in alerts)


def test_portfolio_status_positions_and_daily_report_have_safe_fallback(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=False,
        DEFAULT_SYMBOLS="AAPL",
        ALPACA_API_KEY="",
        ALPACA_SECRET_KEY="",
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        client.post("/api/orders", json={"symbol": "AAPL", "side": "buy", "qty": 1})
        client.post(
            "/api/backtests/run",
            json={"symbol": "AAPL", "days": 60, "seed": 42, "data_source": "synthetic"},
        )
        client.post("/api/simulations/monte-carlo", json={"seed": 7, "paths": 20, "horizon_days": 5})
        status_response = client.get("/api/portfolio/status")
        positions_response = client.get("/api/portfolio/positions")
        report_response = client.get("/api/reports/daily")

    assert status_response.status_code == 200
    status = status_response.json()
    assert status["account"]["configured"] is False
    assert status["account"]["cash"] == 0.0
    assert status["account"]["equity"] == 0.0
    assert status["account"]["buying_power"] == 0.0
    assert status["positions"]["configured"] is False
    assert status["summary"]["positions_count"] == 0
    assert status["summary"]["source"] == "safe_fallback"
    assert status["balance"]["cash"] == 0.0
    assert status["balance"]["equity"] == 0.0
    assert status["balance"]["buying_power"] == 0.0

    assert positions_response.status_code == 200
    assert positions_response.json()["positions"] == []

    assert report_response.status_code == 200
    report = report_response.json()
    assert report["date"] == datetime.now(UTC).date().isoformat()
    assert report["portfolio"]["summary"]["source"] == "safe_fallback"
    assert report["orders"]["count"] == 1
    assert report["orders"]["dry_run_count"] == 1
    assert report["backtests"]["count"] == 1
    assert report["simulations"]["count"] == 1
    assert report["audit_events"]["count"] >= 3
    assert report["alerts"]["count"] >= 0
    assert report["safety"] == {"dry_run": True, "paper_trading_only": True}


def test_active_trades_endpoint_surfaces_local_dry_run_orders_and_signals(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=False,
        DEFAULT_SYMBOLS="AAPL",
        ALPACA_API_KEY="",
        ALPACA_SECRET_KEY="",
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        client.post("/api/orders", json={"symbol": "AAPL", "side": "buy", "qty": 1})
        client.post("/api/scheduler/run-once", json={"symbols": ["AAPL"], "seed": 1})
        response = client.get("/api/trades/active")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["local_orders_count"] >= 1
    assert payload["summary"]["active_trades_count"] >= 1
    assert payload["summary"]["open_alpaca_orders_count"] == 0
    assert payload["local_orders"][0]["symbol"] == "AAPL"
    assert payload["local_orders"][0]["status"] == "dry_run_accepted"
    assert payload["source"] == "local_dry_run_plus_alpaca_if_configured"



def test_scheduler_uses_dynamic_halal_watchlist_when_symbols_are_omitted(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=False,
        ALPACA_API_KEY="",
        ALPACA_SECRET_KEY="",
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        response = client.post("/api/scheduler/run-once", json={"lookback_days": 20, "seed": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["watchlist"]["count"] == 20
    assert len(payload["run"]["symbols"]) == 20
    assert payload["run"]["symbols"] == payload["watchlist"]["symbols"]
    assert "AAPL" not in payload["run"]["symbols"]
    assert payload["no_live_orders_sent"] is True

def test_close_position_endpoint_records_dry_run_exit_order_even_when_entry_risk_limits_would_block(monkeypatch, tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=False,
        DEFAULT_SYMBOLS="AAPL",
        ALPACA_API_KEY="test-key",
        ALPACA_SECRET_KEY="test-secret",
        DRY_RUN=True,
        PAPER_TRADING_ONLY=True,
        MAX_ORDER_NOTIONAL=1000.0,
        MAX_POSITION_NOTIONAL=5000.0,
        MAX_DAILY_ORDERS=1,
        _env_file=None,
    )

    class FakeAlpacaClient:
        def __init__(self, settings):
            self.settings = settings

        def positions(self):
            return {
                "configured": True,
                "source": "alpaca",
                "positions": [
                    {
                        "symbol": "QQQ",
                        "qty": 14.0,
                        "side": "long",
                        "market_value": 9487.38,
                        "avg_entry_price": 676.58,
                        "current_price": 677.67,
                        "unrealized_pl": 15.26,
                        "unrealized_plpc": 0.00161,
                    }
                ],
            }

        def latest_bars(self, symbols):
            return []

        def place_order(self, intent, risk_decision):
            assert risk_decision.allowed is True
            assert risk_decision.estimated_notional == 9487.38
            return OrderSubmission(
                accepted=True,
                status="dry_run_accepted",
                dry_run=True,
                message="DRY_RUN is enabled; no order was sent to Alpaca.",
                order_id="dry-run-close-test",
                raw_response={"intent": intent.model_dump()},
            )

    storage = Storage(settings.database_path)
    storage.record_order(
        OrderIntent(symbol="AAPL", side="buy", qty=1),
        status="dry_run_accepted",
        dry_run=True,
        source="manual",
    )
    monkeypatch.setattr("trading_app.main.AlpacaClient", FakeAlpacaClient)
    app = create_app(settings=settings, storage=storage)

    with ASGITestClient(app) as client:
        response = client.post("/api/positions/QQQ/close", json={"reason": "operator close"})
        orders_response = client.get("/api/orders")
        audit_response = client.get("/api/audit-events")

    assert response.status_code == 200
    payload = response.json()
    assert payload["submission"]["status"] == "dry_run_accepted"
    assert payload["submission"]["dry_run"] is True
    assert payload["risk"]["allowed"] is True
    assert payload["order"]["side"] == "sell"
    assert payload["order"]["qty"] == 14.0
    assert payload["position"]["symbol"] == "QQQ"
    assert orders_response.json()[0]["source"] == "manual_position_close"
    assert audit_response.json()[0]["event_type"] == "position_close_submitted"


def test_close_position_endpoint_reports_missing_position_without_order(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=False,
        DEFAULT_SYMBOLS="AAPL",
        ALPACA_API_KEY="",
        ALPACA_SECRET_KEY="",
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with ASGITestClient(app) as client:
        response = client.post("/api/positions/AAPL/close", json={"reason": "operator close"})
        orders_response = client.get("/api/orders")

    assert response.status_code == 200
    assert response.json()["submission"]["status"] == "no_position"
    assert response.json()["submission"]["dry_run"] is True
    assert orders_response.json() == []
