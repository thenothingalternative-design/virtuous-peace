from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.auth import current_user
from app.models import User, Session, ActiveSession

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────
class StartSession(BaseModel):
    goal:            str
    profile_name:    str
    allowed_apps:    list[str]
    banned_keywords: list[str]
    device_id:       str | None = None

class StopSession(BaseModel):
    duration_s:    int
    blocked_count: int
    block_log:     list[dict] = []
    device_id:     str | None = None
    goal:          str | None = None       
    profile_name:  str | None = None       

class SessionStatus(BaseModel):
    active:              bool
    blocked:             list[str]
    allowed_apps:        list[str]
    goal:                str | None
    started_at:          datetime | None
    started_by:          str | None
    # ── New subscription fields ───────────────────────────────────────────────
    subscription_status: str
    trial_ends_at:       datetime | None
    is_premium:          bool          # convenience flag — True if active or trialing

class SessionOut(BaseModel):
    id:            str
    goal:          str
    profile_name:  str
    started_at:    datetime
    ended_at:      datetime | None
    duration_s:    int
    blocked_count: int
    block_log:     list[dict]
    device_id:     str | None


# ── Status ────────────────────────────────────────────────────────────────────
@router.get("/status", response_model=SessionStatus)
async def session_status(
    user: User = Depends(current_user),
    db:   AsyncSession = Depends(get_db),
):
    active = await db.get(ActiveSession, user.id)

    # Compute is_premium once — active subscribers and trial users get full access
    is_premium = user.subscription_status in ("active", "trialing", "lifetime")

    base = dict(
        subscription_status=user.subscription_status,
        trial_ends_at=user.trial_ends_at,
        is_premium=is_premium,
    )

    if not active:
        return SessionStatus(
            active=False, blocked=[], allowed_apps=[],
            goal=None, started_at=None, started_by=None,
            **base,
        )
    return SessionStatus(
    active=True,
    blocked=active.blocked_sites,
    allowed_apps=active.allowed_apps,
    goal=active.goal,
    started_at=active.started_at,
    started_by=active.started_by,
    subscription_status=user.subscription_status,        # ADD
    trial_ends_at=user.trial_ends_at,                    # ADD
    is_premium=user.subscription_status in ("active", "trialing", "lifetime"),  # ADD
    )

# ── Start ─────────────────────────────────────────────────────────────────────
@router.post("/start", response_model=SessionStatus)
async def start_session(
    body: StartSession,
    user: User = Depends(current_user),
    db:   AsyncSession = Depends(get_db),
):
    existing_active = await db.get(ActiveSession, user.id)
    if existing_active:
        raise HTTPException(status_code=409, detail="A session is already active")

    # Commit the Session row first
    session = Session(
        user_id=user.id,
        goal=body.goal,
        profile_name=body.profile_name,
        started_at=datetime.utcnow(),
        device_id=body.device_id,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)  # ensure session.id is populated

    # Now commit the ActiveSession row separately
    active = ActiveSession(
        user_id=user.id,
        session_id=session.id,
        goal=body.goal,
        blocked_sites=body.banned_keywords,
        allowed_apps=body.allowed_apps,
        started_by=body.device_id,
    )
    db.add(active)
    await db.commit()
    await db.refresh(active)

    return SessionStatus(
    active=True,
    blocked=active.blocked_sites,
    allowed_apps=active.allowed_apps,
    goal=active.goal,
    started_at=active.started_at,
    started_by=active.started_by,
    subscription_status=user.subscription_status,        # ADD
    trial_ends_at=user.trial_ends_at,                    # ADD
    is_premium=user.subscription_status in ("active", "trialing", "lifetime"),  # ADD
    )
    
# ── Stop ──────────────────────────────────────────────────────────────────────
@router.post("/stop", response_model=SessionOut)
async def stop_session(
    body: StopSession,
    user: User = Depends(current_user),
    db:   AsyncSession = Depends(get_db),
):
    is_premium = user.subscription_status in ("active", "trialing", "lifetime")

    # Free users never wrote to active_sessions, so we just save the
    # session record directly without looking for an active_session row
    if not is_premium:
        session = Session(
            user_id=user.id,
            goal=body.goal or "Focus session",
            profile_name=body.profile_name or "Default",
            started_at=datetime.utcnow(),
            ended_at=datetime.utcnow(),
            duration_s=body.duration_s,
            blocked_count=body.blocked_count,
            block_log=body.block_log,
            device_id=body.device_id,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return SessionOut(
            id=session.id,
            goal=session.goal,
            profile_name=session.profile_name,
            started_at=session.started_at,
            ended_at=session.ended_at,
            duration_s=body.duration_s,
            blocked_count=body.blocked_count,
            block_log=body.block_log,
            device_id=body.device_id,
        )

    # Premium users — normal flow
    active = await db.get(ActiveSession, user.id)
    if not active:
        raise HTTPException(status_code=404, detail="No active session found")

    session = await db.get(Session, active.session_id)
    if session:
        session.ended_at      = datetime.utcnow()
        session.duration_s    = body.duration_s
        session.blocked_count = body.blocked_count
        session.block_log     = body.block_log

    await db.delete(active)
    await db.commit()

    if session:
        await db.refresh(session)

    return SessionOut(
        id=session.id if session else active.session_id,
        goal=session.goal if session else active.goal,
        profile_name=session.profile_name if session else "",
        started_at=session.started_at if session else active.started_at,
        ended_at=session.ended_at if session else None,
        duration_s=body.duration_s,
        blocked_count=body.blocked_count,
        block_log=body.block_log,
        device_id=body.device_id,
    )
    
# ── History ───────────────────────────────────────────────────────────────────
@router.get("/history", response_model=list[SessionOut])
async def get_history(
    limit:  int = 120,
    offset: int = 0,
    user:   User = Depends(current_user),
    db:     AsyncSession = Depends(get_db),
):
    is_premium = user.subscription_status in ("active", "trialing")

    query = (
        select(Session)
        .where(Session.user_id == user.id, Session.ended_at != None)
        .order_by(Session.started_at.desc())
        .limit(limit)
        .offset(offset)
    )

    # Free/expired users only see the last 7 days
    if not is_premium:
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=7)
        query = query.where(Session.started_at >= cutoff)

    result = await db.execute(query)
    sessions = result.scalars().all()
    return [
        SessionOut(
            id=s.id, goal=s.goal, profile_name=s.profile_name,
            started_at=s.started_at, ended_at=s.ended_at,
            duration_s=s.duration_s, blocked_count=s.blocked_count,
            block_log=s.block_log, device_id=s.device_id,
        )
        for s in sessions
    ]