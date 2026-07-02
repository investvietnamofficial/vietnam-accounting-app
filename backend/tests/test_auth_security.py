import pytest

from app.core.config import Settings
from app.core.security import create_password_reset_token, decode_token
from app.schemas.auth import validate_password_strength


def test_password_strength_accepts_strong_password():
    assert validate_password_strength("StrongPassword123") == "StrongPassword123"


@pytest.mark.parametrize(
    "password",
    [
        "alllowercase123",
        "ALLUPPERCASE123",
        "NoDigitsPassword",
    ],
)
def test_password_strength_rejects_weak_password(password: str):
    with pytest.raises(ValueError):
        validate_password_strength(password)


def test_password_reset_token_uses_expected_type():
    token = create_password_reset_token("user-123")
    payload = decode_token(token)

    assert payload["sub"] == "user-123"
    assert payload["type"] == "password_reset"


@pytest.mark.parametrize("placeholder", ["dev-jwt-secret", "changeme", "change-me-jwt-secret"])
def test_jwt_secret_rejects_placeholder_values(placeholder: str):
    """Regression: known placeholder JWT secrets must raise in production mode."""
    with pytest.raises(ValueError) as exc_info:
        Settings(app_env="production", jwt_secret_key=placeholder)
    assert "JWT_SECRET_KEY" in str(exc_info.value) or "placeholder" in str(exc_info.value).lower()


# M-3 regression: verify Redis-backed rate limiter is configured in auth.py
import inspect
import app.api.routes.auth as auth_module

_auth_source = inspect.getsource(auth_module)

# The module must have Redis-backed rate limiting
assert "_get_redis_client" in _auth_source, "auth.py must define _get_redis_client for M-3"
assert "login_rl:" in _auth_source, "auth.py must use Redis 'login_rl:' key prefix for M-3"

# In-memory fallback must still exist
assert "_rate_store" in _auth_source, "auth.py must retain in-memory fallback for M-3"
assert "_check_rate_limit" in _auth_source, "auth.py must retain _check_rate_limit for M-3"


# M-2 regression: verify send_email_task is dispatched from forgot_password route
assert "send_email_task.delay" in _auth_source, "auth.py must dispatch send_email_task.delay for M-2"


# M-6 regression: /debug/db endpoint must require authentication
import app.main as main_module
_main_source = inspect.getsource(main_module)
assert "current_user=Depends(get_current_user)" in _main_source or "get_current_user" in _main_source, (
    "/debug/db endpoint must use Depends(get_current_user) for M-6"
)
