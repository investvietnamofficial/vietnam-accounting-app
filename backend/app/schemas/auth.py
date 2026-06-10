"""Authentication and onboarding schemas."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def validate_password_strength(value: str) -> str:
    if not any(ch.islower() for ch in value):
        raise ValueError("Password must contain a lowercase letter")
    if not any(ch.isupper() for ch in value):
        raise ValueError("Password must contain an uppercase letter")
    if not any(ch.isdigit() for ch in value):
        raise ValueError("Password must contain a digit")
    return value


class TokenRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: str
    company_id: str | None
    is_active: bool


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_token: str | None = None


class ResetPasswordRequest(BaseModel):
    reset_token: str = Field(min_length=1)
    new_password: str = Field(min_length=12, max_length=128)


class RegisterCompanyRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    company_name: str = Field(min_length=2, max_length=500)
    company_tax_code: str = Field(min_length=10, max_length=20)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        return validate_password_strength(value)

    @field_validator("company_tax_code")
    @classmethod
    def normalize_tax_code(cls, value: str) -> str:
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) not in (10, 13):
            raise ValueError("Company tax code must be 10 or 13 digits")
        return digits


class RegisterCompanyResponse(BaseModel):
    user: UserSummary
    company_id: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
