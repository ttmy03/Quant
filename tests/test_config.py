from trading_app.config import Settings


def test_settings_default_to_paper_dry_run_mode() -> None:
    settings = Settings()

    assert settings.dry_run is True
    assert settings.paper_trading_only is True
    assert settings.is_paper_endpoint is True
    assert settings.alpaca_configured is False


def test_settings_parse_symbols_from_env_string() -> None:
    settings = Settings(DEFAULT_SYMBOLS="aapl, msft,spy")

    assert settings.default_symbols == ("AAPL", "MSFT", "SPY")
