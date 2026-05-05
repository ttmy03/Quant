from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]
SignalAction = Literal["BUY", "SELL", "HOLD"]
BacktestDataSource = Literal["auto", "alpaca", "synthetic"]


class Bar(BaseModel):
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, value: str) -> str:
        return value.upper()


class Signal(BaseModel):
    symbol: str
    action: SignalAction
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class OrderIntent(BaseModel):
    symbol: str
    side: OrderSide
    qty: float = Field(gt=0)
    order_type: OrderType = "market"
    time_in_force: str = "day"
    limit_price: float | None = Field(default=None, gt=0)

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("side")
    @classmethod
    def lowercase_side(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def require_limit_price_for_limit_orders(self) -> "OrderIntent":
        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("limit_price is required for limit orders")
        return self


class RiskDecision(BaseModel):
    allowed: bool
    reasons: list[str] = Field(default_factory=list)
    estimated_notional: float = 0.0


class OrderSubmission(BaseModel):
    accepted: bool
    status: str
    dry_run: bool
    message: str
    order_id: str | None = None
    raw_response: dict[str, Any] = Field(default_factory=dict)


class KillSwitchRequest(BaseModel):
    enabled: bool = True
    reason: str = Field(default="", max_length=500)


class ControlReasonRequest(BaseModel):
    reason: str = Field(default="", max_length=500)


class ClosePositionRequest(BaseModel):
    reason: str = Field(default="", max_length=500)


class SchedulerRunRequest(BaseModel):
    symbols: list[str] | None = None
    seed: int = 1
    lookback_days: int = Field(default=60, ge=20, le=500)
    qty: float = Field(default=1.0, gt=0)

    @field_validator("symbols")
    @classmethod
    def uppercase_symbols(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [symbol.strip().upper() for symbol in value if symbol.strip()]


class StrategyParamsModel(BaseModel):
    short_window: int = Field(default=5, ge=2, le=250)
    long_window: int = Field(default=20, ge=3, le=500)
    min_crossover_pct: float = Field(default=0.001, ge=0.0, le=0.2)

    @model_validator(mode="after")
    def short_must_be_less_than_long(self) -> "StrategyParamsModel":
        if self.short_window >= self.long_window:
            raise ValueError("short_window must be less than long_window")
        return self


class MonteCarloRequest(BaseModel):
    returns: list[float] | None = None
    initial_value: float = Field(default=10_000.0, gt=0)
    horizon_days: int = Field(default=252, ge=1, le=2520)
    paths: int = Field(default=1000, ge=10, le=100_000)
    seed: int = 42
    ruin_threshold: float = Field(default=0.7, gt=0.0, lt=1.0)


class MonteCarloFanPoint(BaseModel):
    day: int
    p05: float
    p50: float
    p95: float


class MonteCarloHistogramBucket(BaseModel):
    lower: float
    upper: float
    count: int


class MonteCarloSummary(BaseModel):
    seed: int
    paths: int
    horizon_days: int
    initial_value: float
    mean_terminal_value: float
    median_terminal_value: float
    p05_terminal_value: float
    p95_terminal_value: float
    value_at_risk_95: float
    conditional_value_at_risk_95: float
    max_drawdown_p95: float
    probability_of_ruin: float
    mean_terminal_return: float
    fan_chart: list[MonteCarloFanPoint] = Field(default_factory=list)
    terminal_value_histogram: list[MonteCarloHistogramBucket] = Field(default_factory=list)


class BacktestRequest(BaseModel):
    symbol: str = "AAPL"
    days: int = Field(default=252, ge=1, le=5000)
    seed: int = 42
    initial_cash: float = Field(default=10_000.0, gt=0)
    trade_notional: float = Field(default=1_000.0, gt=0)
    data_source: BacktestDataSource = "auto"
    strategy: StrategyParamsModel | None = None

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, value: str) -> str:
        return value.upper()


class BacktestTrade(BaseModel):
    timestamp: datetime
    symbol: str
    side: OrderSide
    qty: float
    price: float
    notional: float
    reason: str


class BacktestEquityPoint(BaseModel):
    timestamp: datetime
    equity: float
    cash: float
    position_qty: float
    close: float


class BacktestMetrics(BaseModel):
    total_return: float
    final_equity: float
    max_drawdown: float
    trades_count: int
    win_rate: float | None = None
    exposure_pct: float
    buy_and_hold_return: float


class BacktestResult(BaseModel):
    symbol: str
    strategy_name: str
    params: StrategyParamsModel
    initial_cash: float
    trade_notional: float
    last_signal: Signal
    trades: list[BacktestTrade] = Field(default_factory=list)
    equity_curve: list[BacktestEquityPoint] = Field(default_factory=list)
    metrics: BacktestMetrics


class ImprovementRequest(BaseModel):
    symbol: str = "AAPL"
    days: int = Field(default=180, ge=40, le=2000)
    seed: int = 42

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, value: str) -> str:
        return value.upper()
