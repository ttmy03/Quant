from __future__ import annotations

from datetime import UTC, datetime

import httpx

from trading_app.alpaca import AlpacaClient
from trading_app.config import Settings


def test_historical_bars_parses_alpaca_stock_bars() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/stocks/AAPL/bars"
        assert request.url.params["timeframe"] == "1Day"
        assert request.url.params["limit"] == "2"
        assert request.headers["APCA-API-KEY-ID"] == "key"
        return httpx.Response(
            200,
            json={
                "bars": [
                    {"t": "2024-01-02T05:00:00Z", "o": 100, "h": 104, "l": 99, "c": 103, "v": 12345},
                    {"t": "2024-01-03T05:00:00Z", "o": 103, "h": 108, "l": 101, "c": 107, "v": 23456},
                ]
            },
        )

    settings = Settings(
        ALPACA_API_KEY="key",
        ALPACA_SECRET_KEY="secret",
        ALPACA_DATA_URL="https://data.alpaca.markets",
        _env_file=None,
    )
    client = AlpacaClient(settings, http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    bars = client.historical_bars("aapl", days=2)

    assert [bar.symbol for bar in bars] == ["AAPL", "AAPL"]
    assert bars[0].timestamp == datetime(2024, 1, 2, 5, tzinfo=UTC)
    assert bars[1].close == 107.0
    assert bars[1].volume == 23456.0


def test_historical_bars_returns_empty_when_alpaca_is_not_configured() -> None:
    settings = Settings(ALPACA_API_KEY="", ALPACA_SECRET_KEY="", _env_file=None)
    client = AlpacaClient(settings)

    assert client.historical_bars("AAPL", days=30) == []


def test_positions_return_safe_fallback_when_alpaca_is_not_configured() -> None:
    settings = Settings(ALPACA_API_KEY="", ALPACA_SECRET_KEY="", _env_file=None)
    client = AlpacaClient(settings)

    payload = client.positions()

    assert payload["configured"] is False
    assert payload["positions"] == []
    assert payload["source"] == "safe_fallback"


def test_positions_parse_alpaca_position_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/positions"
        assert request.headers["APCA-API-KEY-ID"] == "key"
        return httpx.Response(
            200,
            json=[
                {
                    "symbol": "AAPL",
                    "qty": "2",
                    "side": "long",
                    "market_value": "350.50",
                    "avg_entry_price": "170.25",
                    "current_price": "175.25",
                    "unrealized_pl": "10.00",
                    "unrealized_plpc": "0.0294",
                }
            ],
        )

    settings = Settings(
        ALPACA_API_KEY="key",
        ALPACA_SECRET_KEY="secret",
        ALPACA_BASE_URL="https://paper-api.alpaca.markets",
        _env_file=None,
    )
    client = AlpacaClient(settings, http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    payload = client.positions()

    assert payload["configured"] is True
    assert payload["source"] == "alpaca"
    assert payload["positions"] == [
        {
            "symbol": "AAPL",
            "qty": 2.0,
            "side": "long",
            "market_value": 350.5,
            "avg_entry_price": 170.25,
            "current_price": 175.25,
            "unrealized_pl": 10.0,
            "unrealized_plpc": 0.0294,
        }
    ]
