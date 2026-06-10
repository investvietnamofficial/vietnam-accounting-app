import pytest

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
