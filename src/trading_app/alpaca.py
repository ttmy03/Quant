from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Iterable
from uuid import uuid4

import httpx

from trading_app.config import Settings
from trading_app.schemas import Bar, OrderIntent, OrderSubmission, RiskDecision


class AlpacaError(RuntimeError):
    pass


class AlpacaClient:
    """Thin Alpaca HTTP boundary with safe paper/dry-run defaults."""

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.http_client = http_client or httpx.Client(timeout=10)

    def account_status(self) -> dict[str, Any]:
        if not self.settings.alpaca_configured:
            return {
                "configured": False,
                "status": "not_configured",
                "paper_endpoint": self.settings.is_paper_endpoint,
                "cash": 0.0,
                "equity": 0.0,
                "buying_power": 0.0,
                "portfolio_value": 0.0,
                "last_equity": 0.0,
                "message": "Alpaca keys are not configured; dashboard is using safe local mode.",
            }

        payload = self._request("GET", f"{self.settings.alpaca_base_url}/v2/account")
        return {
            "configured": True,
            "status": payload.get("status", "unknown"),
            "paper_endpoint": self.settings.is_paper_endpoint,
            "account_number": payload.get("account_number"),
            "cash": self._float_or_zero(payload.get("cash")),
            "equity": self._float_or_zero(payload.get("equity") or payload.get("portfolio_value")),
            "buying_power": self._float_or_zero(payload.get("buying_power")),
            "portfolio_value": self._float_or_zero(payload.get("portfolio_value")),
            "last_equity": self._float_or_zero(payload.get("last_equity")),
            "currency": payload.get("currency", "USD"),
        }

    def positions(self) -> dict[str, Any]:
        if not self.settings.alpaca_configured:
            return {
                "configured": False,
                "source": "safe_fallback",
                "positions": [],
                "message": "Alpaca keys are not configured; no live position lookup was attempted.",
            }

        payload = self._request("GET", f"{self.settings.alpaca_base_url}/v2/positions")
        return {
            "configured": True,
            "source": "alpaca",
            "positions": [self._parse_position(position) for position in payload],
        }

    def portfolio_status(self, symbols: Iterable[str]) -> dict[str, Any]:
        account = self.account_status()
        positions = self.positions()
        latest_bars = self.latest_bars(symbols)
        position_rows = positions["positions"]
        market_value = sum(float(position.get("market_value") or 0.0) for position in position_rows)
        balance = {
            "cash": self._float_or_zero(account.get("cash")),
            "equity": self._float_or_zero(account.get("equity")),
            "buying_power": self._float_or_zero(account.get("buying_power")),
            "portfolio_value": self._float_or_zero(account.get("portfolio_value")),
            "last_equity": self._float_or_zero(account.get("last_equity")),
            "currency": account.get("currency", "USD"),
        }
        return {
            "account": account,
            "balance": balance,
            "positions": positions,
            "latest_bars": [bar.model_dump(mode="json") for bar in latest_bars],
            "summary": {
                "source": positions["source"],
                "positions_count": len(position_rows),
                "positions_market_value": round(market_value, 4),
                "paper_endpoint": self.settings.is_paper_endpoint,
                "alpaca_configured": self.settings.alpaca_configured,
            },
            "disclaimer": "Research and paper trading only. Not financial advice.",
        }

    def open_orders(self, limit: int = 50) -> dict[str, Any]:
        if not self.settings.alpaca_configured:
            return {
                "configured": False,
                "source": "safe_fallback",
                "orders": [],
                "message": "Alpaca keys are not configured; no open-order lookup was attempted.",
            }
        payload = self._request(
            "GET",
            f"{self.settings.alpaca_base_url}/v2/orders",
            params={"status": "open", "limit": str(limit), "direction": "desc"},
        )
        return {
            "configured": True,
            "source": "alpaca",
            "orders": [self._parse_order(order) for order in payload],
        }

    @staticmethod
    def _float_or_zero(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _parse_position(raw_position: dict[str, Any]) -> dict[str, Any]:
        return {
            "symbol": str(raw_position.get("symbol", "")).upper(),
            "qty": float(raw_position.get("qty") or 0.0),
            "side": raw_position.get("side"),
            "market_value": float(raw_position.get("market_value") or 0.0),
            "avg_entry_price": float(raw_position.get("avg_entry_price") or 0.0),
            "current_price": float(raw_position.get("current_price") or 0.0),
            "unrealized_pl": float(raw_position.get("unrealized_pl") or 0.0),
            "unrealized_plpc": float(raw_position.get("unrealized_plpc") or 0.0),
        }

    @staticmethod
    def _parse_order(raw_order: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": raw_order.get("id"),
            "created_at": raw_order.get("created_at"),
            "submitted_at": raw_order.get("submitted_at"),
            "symbol": str(raw_order.get("symbol", "")).upper(),
            "side": raw_order.get("side"),
            "qty": AlpacaClient._float_or_zero(raw_order.get("qty")),
            "filled_qty": AlpacaClient._float_or_zero(raw_order.get("filled_qty")),
            "type": raw_order.get("type"),
            "status": raw_order.get("status"),
            "limit_price": AlpacaClient._float_or_zero(raw_order.get("limit_price")) if raw_order.get("limit_price") is not None else None,
            "notional": AlpacaClient._float_or_zero(raw_order.get("notional")) if raw_order.get("notional") is not None else None,
        }

    def latest_bars(self, symbols: Iterable[str]) -> list[Bar]:
        symbols = [symbol.upper() for symbol in symbols]
        if not symbols:
            return []

        if not self.settings.alpaca_configured:
            now = datetime.now(UTC)
            return [
                Bar(
                    symbol=symbol,
                    timestamp=now,
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.0,
                    volume=0.0,
                )
                for symbol in symbols
            ]

        payload = self._request(
            "GET",
            f"{self.settings.alpaca_data_url}/v2/stocks/bars/latest",
            params={"symbols": ",".join(symbols)},
        )
        bars: list[Bar] = []
        for symbol, raw_bar in (payload.get("bars") or {}).items():
            bars.append(self._parse_bar(symbol, raw_bar))
        return bars

    def historical_bars(self, symbol: str, *, days: int, timeframe: str = "1Day") -> list[Bar]:
        symbol = symbol.upper()
        if not self.settings.alpaca_configured:
            return []

        end = datetime.now(UTC)
        # Ask for extra calendar days so weekends/holidays still leave enough daily bars.
        start = end - timedelta(days=max(days * 3, days + 10))
        payload = self._request(
            "GET",
            f"{self.settings.alpaca_data_url}/v2/stocks/{symbol}/bars",
            params={
                "timeframe": timeframe,
                "start": start.isoformat().replace("+00:00", "Z"),
                "end": end.isoformat().replace("+00:00", "Z"),
                "limit": str(days),
                "adjustment": "raw",
                "feed": "iex",
            },
        )
        returned_bars = [self._parse_bar(symbol, raw_bar) for raw_bar in payload.get("bars", [])]
        return returned_bars[-days:]

    @staticmethod
    def _parse_bar(symbol: str, raw_bar: dict[str, Any]) -> Bar:
        return Bar(
            symbol=symbol,
            timestamp=datetime.fromisoformat(raw_bar["t"].replace("Z", "+00:00")),
            open=float(raw_bar["o"]),
            high=float(raw_bar["h"]),
            low=float(raw_bar["l"]),
            close=float(raw_bar["c"]),
            volume=float(raw_bar.get("v", 0.0)),
        )

    def place_order(self, intent: OrderIntent, risk_decision: RiskDecision) -> OrderSubmission:
        if not risk_decision.allowed:
            return OrderSubmission(
                accepted=False,
                status="rejected_by_risk",
                dry_run=self.settings.dry_run,
                message="Order rejected by risk guard.",
                raw_response={"risk_reasons": risk_decision.reasons},
            )

        if self.settings.paper_trading_only and not self.settings.is_paper_endpoint:
            return OrderSubmission(
                accepted=False,
                status="rejected_non_paper_endpoint",
                dry_run=self.settings.dry_run,
                message="PAPER_TRADING_ONLY blocks the configured Alpaca endpoint.",
            )

        if self.settings.dry_run:
            dry_run_id = f"dry-run-{uuid4()}"
            return OrderSubmission(
                accepted=True,
                status="dry_run_accepted",
                dry_run=True,
                message="DRY_RUN is enabled; no order was sent to Alpaca.",
                order_id=dry_run_id,
                raw_response={"id": dry_run_id, "intent": intent.model_dump()},
            )

        if not self.settings.alpaca_configured:
            return OrderSubmission(
                accepted=False,
                status="rejected_missing_credentials",
                dry_run=False,
                message="Alpaca credentials are not configured.",
            )

        payload: dict[str, Any] = {
            "symbol": intent.symbol,
            "qty": str(intent.qty),
            "side": intent.side,
            "type": intent.order_type,
            "time_in_force": intent.time_in_force,
        }
        if intent.limit_price is not None:
            payload["limit_price"] = str(intent.limit_price)

        response = self._request("POST", f"{self.settings.alpaca_base_url}/v2/orders", json=payload)
        return OrderSubmission(
            accepted=True,
            status=response.get("status", "submitted"),
            dry_run=False,
            message="Paper order submitted to Alpaca.",
            order_id=response.get("id"),
            raw_response=response,
        )

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        headers = kwargs.pop("headers", {})
        headers.update(
            {
                "APCA-API-KEY-ID": self.settings.alpaca_api_key or "",
                "APCA-API-SECRET-KEY": self.settings.alpaca_secret_key or "",
            }
        )
        response = self.http_client.request(method, url, headers=headers, **kwargs)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AlpacaError(f"Alpaca request failed: {exc.response.status_code} {exc.response.text}") from exc
        return response.json()
