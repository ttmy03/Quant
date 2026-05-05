from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from trading_app.watchlist import HALAL_MSCI_WORLD_LARGE_CAP_SYMBOLS


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables and .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", enable_decoding=False)

    app_name: str = "Paper Quant"
    environment: str = Field(default="development", validation_alias="APP_ENV")

    alpaca_api_key: str | None = Field(default=None, validation_alias="ALPACA_API_KEY")
    alpaca_secret_key: str | None = Field(default=None, validation_alias="ALPACA_SECRET_KEY")
    alpaca_base_url: str = Field(
        default="https://paper-api.alpaca.markets",
        validation_alias="ALPACA_BASE_URL",
    )
    alpaca_data_url: str = Field(
        default="https://data.alpaca.markets",
        validation_alias="ALPACA_DATA_URL",
    )

    dry_run: bool = Field(default=True, validation_alias="DRY_RUN")
    paper_trading_only: bool = Field(default=True, validation_alias="PAPER_TRADING_ONLY")

    auth_enabled: bool = Field(default=True, validation_alias="AUTH_ENABLED")
    admin_username: str = Field(default="admin", validation_alias="ADMIN_USERNAME")
    admin_password_hash: str | None = Field(default=None, validation_alias="ADMIN_PASSWORD_HASH")
    admin_password: str | None = Field(default=None, validation_alias="ADMIN_PASSWORD")
    session_secret: str | None = Field(default=None, validation_alias="SESSION_SECRET")
    session_cookie_name: str = Field(
        default="paper_quant_session",
        validation_alias="SESSION_COOKIE_NAME",
    )
    session_max_age_seconds: int = Field(
        default=86400,
        validation_alias="SESSION_MAX_AGE_SECONDS",
    )

    database_path: Path = Field(
        default=Path("data/paper_quant.sqlite3"),
        validation_alias="DATABASE_PATH",
    )
    default_symbols: tuple[str, ...] = Field(
        default=HALAL_MSCI_WORLD_LARGE_CAP_SYMBOLS,
        validation_alias="DEFAULT_SYMBOLS",
    )

    max_order_notional: float = Field(default=1000.0, validation_alias="MAX_ORDER_NOTIONAL")
    max_position_notional: float = Field(
        default=5000.0,
        validation_alias="MAX_POSITION_NOTIONAL",
    )
    max_daily_orders: int = Field(default=10, validation_alias="MAX_DAILY_ORDERS")
    max_strategy_drawdown: float = Field(
        default=0.25,
        validation_alias="MAX_STRATEGY_DRAWDOWN",
    )
    max_probability_of_ruin: float = Field(
        default=0.05,
        validation_alias="MAX_PROBABILITY_OF_RUIN",
    )

    @field_validator("default_symbols", mode="before")
    @classmethod
    def parse_symbols(cls, value: Any) -> tuple[str, ...]:
        if value is None or value == "":
            return ()
        if isinstance(value, str):
            return tuple(symbol.strip().upper() for symbol in value.split(",") if symbol.strip())
        return tuple(str(symbol).strip().upper() for symbol in value if str(symbol).strip())

    @field_validator("alpaca_base_url", "alpaca_data_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def alpaca_configured(self) -> bool:
        return bool(self.alpaca_api_key and self.alpaca_secret_key)

    @property
    def is_paper_endpoint(self) -> bool:
        return "paper" in self.alpaca_base_url.lower()

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def effective_session_secret(self) -> str:
        if self.session_secret:
            return self.session_secret
        return "development-only-paper-quant-session-secret"

    @property
    def auth_credentials_configured(self) -> bool:
        return bool(self.admin_password_hash or self.admin_password)

    def validate_auth_configuration(self) -> None:
        if not self.auth_enabled:
            return
        if self.is_production and not self.session_secret:
            raise RuntimeError("SESSION_SECRET is required when AUTH_ENABLED=true in production.")
        if self.is_production and not self.auth_credentials_configured:
            raise RuntimeError("ADMIN_PASSWORD_HASH or ADMIN_PASSWORD is required when AUTH_ENABLED=true in production.")

    def public_dict(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "environment": self.environment,
            "auth_enabled": self.auth_enabled,
            "auth_credentials_configured": self.auth_credentials_configured,
            "session_cookie_name": self.session_cookie_name,
            "session_max_age_seconds": self.session_max_age_seconds,
            "alpaca_configured": self.alpaca_configured,
            "alpaca_base_url": self.alpaca_base_url,
            "dry_run": self.dry_run,
            "paper_trading_only": self.paper_trading_only,
            "database_path": str(self.database_path),
            "default_symbols": list(self.default_symbols),
            "max_order_notional": self.max_order_notional,
            "max_position_notional": self.max_position_notional,
            "max_daily_orders": self.max_daily_orders,
            "max_strategy_drawdown": self.max_strategy_drawdown,
            "max_probability_of_ruin": self.max_probability_of_ruin,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
