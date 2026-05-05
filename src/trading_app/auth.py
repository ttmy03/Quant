from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Request

from trading_app.config import Settings


PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 260_000


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str, iterations: int = PASSWORD_HASH_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{PASSWORD_HASH_ALGORITHM}${iterations}${_base64url_encode(salt)}${_base64url_encode(digest)}"


def verify_password_hash(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, expected_text = password_hash.split("$", 3)
        iterations = int(iterations_text)
        salt = _base64url_decode(salt_text)
        expected = _base64url_decode(expected_text)
    except (TypeError, ValueError, binascii.Error):
        return False

    if algorithm != PASSWORD_HASH_ALGORITHM or iterations <= 0:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    expires_at: int


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def authenticate(self, username: str, password: str) -> bool:
        if not self.settings.auth_credentials_configured:
            return False
        if not hmac.compare_digest(username, self.settings.admin_username):
            return False
        if self.settings.admin_password_hash:
            return verify_password_hash(password, self.settings.admin_password_hash)
        return hmac.compare_digest(password, self.settings.admin_password or "")

    def create_session_cookie(self, username: str) -> str:
        now = int(time.time())
        payload = {
            "sub": username,
            "iat": now,
            "exp": now + self.settings.session_max_age_seconds,
        }
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        payload_text = _base64url_encode(payload_bytes)
        signature = self._sign(payload_text)
        return f"{payload_text}.{signature}"

    def read_session(self, request: Request) -> AuthenticatedUser | None:
        cookie = request.cookies.get(self.settings.session_cookie_name)
        if not cookie:
            return None

        try:
            payload_text, signature = cookie.split(".", 1)
            expected_signature = self._sign(payload_text)
            if not hmac.compare_digest(signature, expected_signature):
                return None
            payload = json.loads(_base64url_decode(payload_text))
        except (ValueError, json.JSONDecodeError, binascii.Error):
            return None

        username = payload.get("sub")
        expires_at = payload.get("exp")
        if not isinstance(username, str) or not isinstance(expires_at, int):
            return None
        if username != self.settings.admin_username or expires_at < int(time.time()):
            return None
        return AuthenticatedUser(username=username, expires_at=expires_at)

    def _sign(self, payload_text: str) -> str:
        digest = hmac.new(
            self.settings.effective_session_secret.encode("utf-8"),
            payload_text.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return _base64url_encode(digest)


def auth_state(settings: Settings, user: AuthenticatedUser | None) -> dict[str, Any]:
    return {
        "auth_enabled": settings.auth_enabled,
        "authenticated": (not settings.auth_enabled) or user is not None,
        "user": {"username": user.username, "expires_at": user.expires_at} if user else None,
        "safety": {
            "dry_run": settings.dry_run,
            "paper_trading_only": settings.paper_trading_only,
            "paper_endpoint": settings.is_paper_endpoint,
            "alpaca_configured": settings.alpaca_configured,
        },
    }
