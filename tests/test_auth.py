import pytest

from trading_app.auth import AuthService, hash_password
from trading_app.config import Settings


def test_password_hash_authenticates_without_plain_password() -> None:
    settings = Settings(
        AUTH_ENABLED=True,
        ADMIN_PASSWORD_HASH=hash_password("test-password"),
        _env_file=None,
    )

    auth = AuthService(settings)

    assert auth.authenticate("admin", "test-password") is True
    assert auth.authenticate("admin", "wrong-password") is False


def test_production_auth_requires_secret_and_credentials() -> None:
    settings = Settings(APP_ENV="production", AUTH_ENABLED=True, _env_file=None)

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        settings.validate_auth_configuration()

    settings = Settings(
        APP_ENV="production",
        AUTH_ENABLED=True,
        SESSION_SECRET="test-session-secret",
        _env_file=None,
    )

    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD_HASH"):
        settings.validate_auth_configuration()
