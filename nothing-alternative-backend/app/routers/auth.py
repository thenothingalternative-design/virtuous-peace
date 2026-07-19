from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import (
    verify_google_token, verify_apple_token,
    upsert_user, create_jwt, current_user,
    exchange_google_code,   # ← the helper from auth.py, NOT redefined below
)
from app.models import User

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────
class GoogleCodeExchange(BaseModel):     # defined ONCE
    code:         str
    redirect_uri: str

class GoogleSignIn(BaseModel):
    id_token: str

class AppleSignIn(BaseModel):
    id_token:     str
    email:        str | None = None
    display_name: str | None = None

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user_id:      str
    email:        str
    display_name: str | None


# ── Google (id_token path — mobile SDK) ──────────────────────────────────────
@router.post("/google", response_model=TokenResponse)
async def sign_in_google(body: GoogleSignIn, db: AsyncSession = Depends(get_db)):
    payload = await verify_google_token(body.id_token)
    user = await upsert_user(
        db, google_id=payload["sub"],
        email=payload["email"], display_name=payload.get("name"),
    )
    return TokenResponse(
        access_token=create_jwt(user.id), user_id=user.id,
        email=user.email, display_name=user.display_name,
    )


# ── Google (auth-code path — desktop local-redirect flow) ────────────────────
@router.post("/google/exchange", response_model=TokenResponse)
async def sign_in_google_exchange(          # ← different name from the imported helper
    body: GoogleCodeExchange,
    db: AsyncSession = Depends(get_db),
):
    token_resp = await exchange_google_code(body.code, body.redirect_uri)
    id_token = token_resp.get("id_token")
    if not id_token:
        raise HTTPException(
            status_code=400,
            detail=f"Google token exchange failed: {token_resp}",
        )
    payload = await verify_google_token(id_token)
    user = await upsert_user(
        db, google_id=payload["sub"],
        email=payload["email"], display_name=payload.get("name"),
    )
    return TokenResponse(
        access_token=create_jwt(user.id), user_id=user.id,
        email=user.email, display_name=user.display_name,
    )


# ── Apple ─────────────────────────────────────────────────────────────────────
@router.post("/apple", response_model=TokenResponse)
async def sign_in_apple(body: AppleSignIn, db: AsyncSession = Depends(get_db)):
    payload = await verify_apple_token(body.id_token)
    email = payload.get("email") or body.email
    if not email:
        raise HTTPException(
            status_code=400,
            detail="Email required — include it in the request body after first sign-in",
        )
    user = await upsert_user(
        db, apple_id=payload["sub"],
        email=email, display_name=body.display_name,
    )
    return TokenResponse(
        access_token=create_jwt(user.id), user_id=user.id,
        email=user.email, display_name=user.display_name,
    )


# ── Me ────────────────────────────────────────────────────────────────────────
@router.get("/me", response_model=TokenResponse)
async def me(user: User = Depends(current_user)):
    return TokenResponse(
        access_token="", user_id=user.id,
        email=user.email, display_name=user.display_name,
    )