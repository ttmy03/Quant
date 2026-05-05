from fastapi.testclient import TestClient

from trading_app.config import Settings
from trading_app.main import create_app
from trading_app.storage import Storage


def test_health_endpoint(tmp_path) -> None:
    settings = Settings(DATABASE_PATH=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["dry_run"] is True


def test_order_endpoint_records_dry_run_order(tmp_path) -> None:
    settings = Settings(DATABASE_PATH=tmp_path / "test.sqlite3", DEFAULT_SYMBOLS="AAPL")
    app = create_app(settings=settings, storage=Storage(settings.database_path))

    with TestClient(app) as client:
        response = client.post("/api/orders", json={"symbol": "AAPL", "side": "buy", "qty": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["submission"]["status"] == "dry_run_accepted"
    assert payload["order"]["dry_run"] is True
