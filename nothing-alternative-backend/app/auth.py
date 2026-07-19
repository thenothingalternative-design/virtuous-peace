import os
import time
import httpx
import jwt as pyjwt
from jwt import PyJWKClient
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import User

# ── Config ────────────────────────────────────────────────────────────────────
JWT_SECRET     = os.environ["JWT_SECRET"]          # long random string you set
JWT_ALGORITHM  = "HS256"
JWT_EXPIRE_DAYS = 90                               # long-lived — mobile UX

GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
APPLE_CLIENT_ID  = os.environ.get("APPLE_CLIENT_ID", "")  # optional until iOS
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")  # only needed for server-side flow

_bearer = HTTPBearer()

# ── Google code exchange (for desktop local-redirect OAuth) ──────────────────
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

async def exchange_google_code(code: str, redirect_uri: str) -> dict:
    if not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=501, detail="GOOGLE_CLIENT_SECRET not configured")
    async with httpx.AsyncClient() as client:
        r = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        return r.json()
    
# ── JWT ───────────────────────────────────────────────────────────────────────
def create_jwt(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(days=JWT_EXPIRE_DAYS),
        "iat": datetime.utcnow(),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict:
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_jwt(credentials.credentials)
    user = await db.get(User, payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ── Google OAuth ──────────────────────────────────────────────────────────────
_GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_google_jwks: PyJWKClient | None = None

def _get_google_jwks() -> PyJWKClient:
    global _google_jwks
    if _google_jwks is None:
        _google_jwks = PyJWKClient(_GOOGLE_CERTS_URL)
    return _google_jwks


async def verify_google_token(id_token: str) -> dict:
    """
    Verifies a Google ID token from the client and returns the payload.
    The client (app) obtains this token via Google Sign-In SDK.
    """
    jwks = _get_google_jwks()
    try:
        signing_key = jwks.get_signing_key_from_jwt(id_token)
        payload = pyjwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=GOOGLE_CLIENT_ID,
        )
        return payload
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Google token: {e}")


# ── Apple OAuth ───────────────────────────────────────────────────────────────
_APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
_apple_jwks: PyJWKClient | None = None

def _get_apple_jwks() -> PyJWKClient:
    global _apple_jwks
    if _apple_jwks is None:
        _apple_jwks = PyJWKClient(_APPLE_JWKS_URL)
    return _apple_jwks


async def verify_apple_token(id_token: str) -> dict:
    """
    Verifies an Apple ID token. Note: Apple only sends email on first sign-in.
    The client must cache and send it along with the token after that.
    """
    if not APPLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Apple Sign-In not configured")
    jwks = _get_apple_jwks()
    try:
        signing_key = jwks.get_signing_key_from_jwt(id_token)
        payload = pyjwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=APPLE_CLIENT_ID,
        )
        return payload
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Apple token: {e}")


# ── Upsert user ───────────────────────────────────────────────────────────────
from datetime import datetime, timedelta

TRIAL_DAYS = 7

async def upsert_user(
    db: AsyncSession,
    *,
    google_id: str | None = None,
    apple_id:  str | None = None,
    email: str,
    display_name: str | None = None,
) -> User:
    """Find or create user by provider ID, keeping email up to date."""
    user: User | None = None

    if google_id:
        result = await db.execute(select(User).where(User.google_id == google_id))
        user = result.scalar_one_or_none()
    elif apple_id:
        result = await db.execute(select(User).where(User.apple_id == apple_id))
        user = result.scalar_one_or_none()

    if not user:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

    if user:
        if google_id and not user.google_id:
            user.google_id = google_id
        if apple_id and not user.apple_id:
            user.apple_id = apple_id
        if display_name and not user.display_name:
            user.display_name = display_name
        user.last_seen_at = datetime.utcnow()

        # If they're still marked trialing but the trial has expired, downgrade them
        if (
            user.subscription_status == "trialing"
            and user.trial_ends_at
            and datetime.utcnow() > user.trial_ends_at
        ):
            user.subscription_status = "expired"
    else:
        # Brand new user — start 7-day trial
        user = User(
            email=email,
            google_id=google_id,
            apple_id=apple_id,
            display_name=display_name,
            subscription_status="trialing",
            trial_ends_at=datetime.utcnow() + timedelta(days=TRIAL_DAYS),
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)
    return user
