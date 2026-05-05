from fastapi.testclient import TestClient

from trading_app.config import Settings
from trading_app.main import create_app
from trading_app.storage import Storage


def test_health_endpoint(tmp_path) -> None:
    settings = Settings(
        DATABASE_PATH=tmp_path / "test.sqlite3",
        AUTH_ENABLED=True,
        ADMIN_PASSWORD="test-password",
        SESSION_SECRET="test-session-secret",
        _env_file=None,
    )
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with TestClient(app) as client:
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

    with TestClient(app) as client:
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

    with TestClient(app) as client:
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

    with TestClient(app) as client:
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

    with TestClient(app) as client:
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

    with TestClient(app) as client:
        response = client.post("/api/orders", json={"symbol": "AAPL", "side": "buy", "qty": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["submission"]["status"] == "dry_run_accepted"
    assert payload["order"]["dry_run"] is True
