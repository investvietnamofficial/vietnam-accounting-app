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
