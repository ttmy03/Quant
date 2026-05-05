from trading_app.config import Settings


def test_settings_default_to_paper_dry_run_mode() -> None:
    settings = Settings(_env_file=None)

    assert settings.dry_run is True
    assert settings.paper_trading_only is True
    assert settings.is_paper_endpoint is True
    assert settings.alpaca_configured is False
    assert settings.auth_enabled is True
    assert settings.session_cookie_name == "paper_quant_session"


def test_settings_parse_symbols_from_env_string() -> None:
    settings = Settings(DEFAULT_SYMBOLS="aapl, msft,spy", _env_file=None)

    assert settings.default_symbols == ("AAPL", "MSFT", "SPY")
