"""Auth routes — login, refresh, register, password reset."""

import time
from collections import defaultdict
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
from app.services.email.email_service import get_email_service
from app.workers.tasks import send_email_task

router = APIRouter()
settings = get_settings()

# ── In-memory rate limiter: 5 login attempts per minute per IP ───────────────
# M-3 upgrade: replaced by Redis-backed limiter below, kept as fallback.
_login_lock = Lock()
_rate_store: dict[str, list[float]] = defaultdict(list)

_LOGIN_RATE_LIMIT = 5
_LOGIN_WINDOW_SECS = 60

# M-3: Redis-backed rate limiter using settings.redis_url.
# Falls back to in-memory store if Redis is unavailable.
_redis_client = None


def _get_redis_client():
    """Lazily initialise a Redis client. Returns None if unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis
        _redis_client = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_client = None
        return None


def _check_rate_limit(ip: str) -> bool:
    """
    Return True if the login request from `ip` is allowed.
    Uses Redis SETEX + INCR when available; falls back to the in-memory store.
    """
    client = _get_redis_client()
    key = f"login_rl:{ip}"

    if client is not None:
        try:
            # Atomic: SETEX sets expiry, INCR increments — both in one round-trip.
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, _LOGIN_WINDOW_SECS)
            results = pipe.execute()
            count = results[0]
            return count <= _LOGIN_RATE_LIMIT
        except Exception:
            # Redis error — fall through to in-memory fallback
            pass

    # In-memory fallback (process-local; does not survive restarts)
    now = time.time()
    with _login_lock:
        window = [t for t in _rate_store[ip] if now - t < _LOGIN_WINDOW_SECS]
        _rate_store[ip] = window
        if len(window) >= _LOGIN_RATE_LIMIT:
            return False
        window.append(now)
        return True


@router.post("/token", response_model=AuthTokenResponse)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait a minute before trying again.",
        )
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
async def refresh_token(
    payload: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    decoded = decode_token(payload.refresh_token)
    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    # Re-validate user exists and is active — prevents deactivated users from
    # continuing to mint access tokens via a stolen refresh token
    user_id = decoded["sub"]
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive — please log in again",
        )

    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),  # rotate refresh token on each use
        "token_type": "bearer",
    }


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

    # Always return the same message to avoid email enumeration
    message = "If the account exists, a password reset email has been sent."

    if user and user.is_active:
        reset_token = create_password_reset_token(user.id)
        # M-2: dispatch email as background Celery task — fire-and-forget from
        # the HTTP response path; Celery retries on failure independently.
        if settings.use_celery:
            send_email_task.delay(user.email, reset_token)
        else:
            # Fallback for local development without a Celery worker
            get_email_service().send_password_reset_email(user.email, reset_token)

    return {"message": message}


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
