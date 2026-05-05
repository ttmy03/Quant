from __future__ import annotations

from datetime import UTC, datetime
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
                "message": "Alpaca keys are not configured; dashboard is using safe local mode.",
            }

        payload = self._request("GET", f"{self.settings.alpaca_base_url}/v2/account")
        return {
            "configured": True,
            "status": payload.get("status", "unknown"),
            "paper_endpoint": self.settings.is_paper_endpoint,
            "account_number": payload.get("account_number"),
            "buying_power": payload.get("buying_power"),
            "portfolio_value": payload.get("portfolio_value"),
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
            bars.append(
                Bar(
                    symbol=symbol,
                    timestamp=datetime.fromisoformat(raw_bar["t"].replace("Z", "+00:00")),
                    open=float(raw_bar["o"]),
                    high=float(raw_bar["h"]),
                    low=float(raw_bar["l"]),
                    close=float(raw_bar["c"]),
                    volume=float(raw_bar.get("v", 0.0)),
                )
            )
        return bars

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
