from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database import get_db
from app.auth import current_user
from app.models import User, Profile

router = APIRouter()

_DEFAULT_ALLOWED   = ["browsers"]
# "chrome", "firefox", "brave", "browser", 'edge', 'opera', 'samsung', 'duckduckgo', 'vivaldi', 'yandex', 'tor', 'maxthon'
_DEFAULT_BANNED    = ["youtube", "facebook", "instagram", "twitter",
                      "x.com", "reddit", "tiktok", "netflix"]


# ── Schemas ───────────────────────────────────────────────────────────────────
class ProfileIn(BaseModel):
    name:            str
    allowed_apps:    list[str] = _DEFAULT_ALLOWED
    banned_keywords: list[str] = _DEFAULT_BANNED
    is_active:       bool = False

class ProfileOut(ProfileIn):
    id:         str
    updated_at: datetime

class ProfilesSync(BaseModel):
    """
    Full profile list from a device — replaces whatever is on the server.
    Send all profiles, mark exactly one as is_active=True.
    """
    profiles:       list[ProfileIn]
    active_profile: str            # name of the active profile


# ── GET all profiles ──────────────────────────────────────────────────────────
@router.get("/", response_model=list[ProfileOut])
async def get_profiles(
    user: User = Depends(current_user),
    db:   AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Profile).where(Profile.user_id == user.id).order_by(Profile.created_at)
    )
    profiles = result.scalars().all()

    # Seed a Default profile if the user has none
    if not profiles:
        default = Profile(
            user_id=user.id,
            name="Default",
            allowed_apps=list(_DEFAULT_ALLOWED),
            banned_keywords=list(_DEFAULT_BANNED),
            is_active=True,
        )
        db.add(default)
        await db.commit()
        await db.refresh(default)
        profiles = [default]

    return [
        ProfileOut(
            id=p.id, name=p.name,
            allowed_apps=p.allowed_apps,
            banned_keywords=p.banned_keywords,
            is_active=p.is_active,
            updated_at=p.updated_at,
        )
        for p in profiles
    ]


# ── PUT — full sync (device pushes its entire profile list) ──────────────────

@router.put("/", response_model=list[ProfileOut])
async def sync_profiles(
    body: ProfilesSync,
    user: User = Depends(current_user),
    db:   AsyncSession = Depends(get_db),
):
    is_premium = user.subscription_status in ("active", "trialing", "lifetime")
    FREE_PROFILE_LIMIT = 1

    if not is_premium and len(body.profiles) > FREE_PROFILE_LIMIT:
        raise HTTPException(
            status_code=403,
            detail="Free accounts support 1 profile. Upgrade to Premium to create unlimited profiles."
        )
        
    """
    Replaces all server profiles with the device's version.
    Called when the user makes any change in the app (add profile, toggle app, etc.)
    Last-write-wins — fine for a single-user app.
    """
    # Fetch existing profiles to preserve IDs where possible
    result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    existing = {p.name: p for p in result.scalars().all()}

    # Delete profiles that no longer exist on the device
    incoming_names = {p.name for p in body.profiles}
    for name, prof in existing.items():
        if name not in incoming_names:
            await db.delete(prof)

    saved = []
    for p_in in body.profiles:
        is_active = (p_in.name == body.active_profile)
        if p_in.name in existing:
            prof = existing[p_in.name]
            prof.allowed_apps    = p_in.allowed_apps
            prof.banned_keywords = p_in.banned_keywords
            prof.is_active       = is_active
            prof.updated_at      = datetime.utcnow()
        else:
            prof = Profile(
                user_id=user.id,
                name=p_in.name,
                allowed_apps=p_in.allowed_apps,
                banned_keywords=p_in.banned_keywords,
                is_active=is_active,
            )
            db.add(prof)
        saved.append(prof)

    await db.commit()
    for p in saved:
        await db.refresh(p)

    return [
        ProfileOut(
            id=p.id, name=p.name,
            allowed_apps=p.allowed_apps,
            banned_keywords=p.banned_keywords,
            is_active=p.is_active,
            updated_at=p.updated_at,
        )
        for p in saved
    ]
