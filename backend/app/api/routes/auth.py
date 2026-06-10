"""Auth routes — login, refresh, register, password reset."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.models import Company, User, UserRole
from app.schemas.auth import (
    AuthTokenResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    RegisterCompanyRequest,
    RegisterCompanyResponse,
    ResetPasswordRequest,
    TokenRefreshRequest,
    UserSummary,
    validate_password_strength,
)

router = APIRouter()
settings = get_settings()


@router.post("/token", response_model=AuthTokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == form.username.strip().lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
    }


@router.post("/token/refresh", response_model=AuthTokenResponse)
async def refresh_token(payload: TokenRefreshRequest):
    decoded = decode_token(payload.refresh_token)
    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    return {"access_token": create_access_token(decoded["sub"]), "token_type": "bearer"}


@router.get("/me", response_model=UserSummary)
async def get_me(current_user=Depends(get_current_user)):
    return current_user


@router.post("/register", response_model=RegisterCompanyResponse, status_code=201)
async def register(
    payload: RegisterCompanyRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new tenant and initial admin user."""
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    company_existing = await db.execute(select(Company).where(Company.tax_code == payload.company_tax_code))
    if company_existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Company tax code already registered")

    company = Company(
        name=payload.company_name,
        tax_code=payload.company_tax_code,
        accounting_standard="TT200",
    )
    db.add(company)
    await db.flush()
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.ADMIN,
        company_id=company.id,
    )
    db.add(user)
    await db.commit()
    return {
        "user": user,
        "company_id": company.id,
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
    }


@router.post("/password/forgot", response_model=ForgotPasswordResponse)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email.strip().lower()))
    user = result.scalar_one_or_none()
    reset_token = create_password_reset_token(user.id) if user and user.is_active else None
    return {
        "message": "If the account exists, password reset instructions have been generated.",
        "reset_token": reset_token if not settings.is_production else None,
    }


@router.post("/password/reset", response_model=AuthTokenResponse)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    decoded = decode_token(payload.reset_token)
    if decoded.get("type") != "password_reset":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    result = await db.execute(select(User).where(User.id == decoded.get("sub")))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    validated_password = validate_password_strength(payload.new_password)
    user.hashed_password = hash_password(validated_password)
    await db.commit()
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
    }
