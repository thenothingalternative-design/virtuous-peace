# Valid subscription_status values:
# "trialing"  — 7-day free trial
# "active"    — paying subscriber (monthly or yearly)
# "lifetime"  — one-time purchase, never expires
# "cancelled" — subscription cancelled, access until current_period_end
# "past_due"  — payment failed
# "expired"   — trial ended, no payment
# "free"      — explicitly on free tier

import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, Float, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


def _uuid():
    return str(uuid.uuid4())


import enum

class SubscriptionStatus(str, enum.Enum):
    free      = "free"
    trialing  = "trialing"
    active    = "active"
    lifetime  = "lifetime"
    cancelled = "cancelled"
    past_due  = "past_due"
    expired   = "expired"

class User(Base):
    __tablename__ = "users"

    id:                  Mapped[str]  = mapped_column(String, primary_key=True, default=_uuid)
    email:               Mapped[str]  = mapped_column(String, unique=True, index=True, nullable=False)
    google_id:           Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)
    apple_id:            Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)
    display_name:        Mapped[str | None] = mapped_column(String, nullable=True)
    created_at:          Mapped[datetime]   = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at:        Mapped[datetime]   = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── Subscription ──────────────────────────────────────────────────────────
    subscription_status: Mapped[str] = mapped_column(
        String, default=SubscriptionStatus.trialing, nullable=False
    )
    trial_ends_at:       Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stripe_customer_id:  Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    current_period_end:  Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    profiles:       Mapped[list["Profile"]]      = relationship("Profile",       back_populates="user", cascade="all, delete-orphan")
    sessions:       Mapped[list["Session"]]      = relationship("Session",       back_populates="user", cascade="all, delete-orphan")
    active_session: Mapped["ActiveSession | None"] = relationship("ActiveSession", back_populates="user", uselist=False, cascade="all, delete-orphan")


class Profile(Base):
    """
    A named focus profile belonging to a user.
    allowed_apps and banned_keywords are stored as JSON arrays.
    """
    __tablename__ = "profiles"

    id:              Mapped[str]  = mapped_column(String, primary_key=True, default=_uuid)
    user_id:         Mapped[str]  = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    name:            Mapped[str]  = mapped_column(String, nullable=False)           # e.g. "Default", "Deep Work"
    allowed_apps:    Mapped[list] = mapped_column(JSON, default=list)               # ["resolve", "matlab"]
    banned_keywords: Mapped[list] = mapped_column(JSON, default=list)               # ["youtube", "reddit"]
    is_active:       Mapped[bool] = mapped_column(Boolean, default=False)           # which profile is currently selected
    created_at:      Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at:      Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="profiles")


class Session(Base):
    """
    A completed (or in-progress) focus session — historical record.
    """
    __tablename__ = "sessions"

    id:           Mapped[str]       = mapped_column(String, primary_key=True, default=_uuid)
    user_id:      Mapped[str]       = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    goal:         Mapped[str]       = mapped_column(Text, nullable=False)
    profile_name: Mapped[str]       = mapped_column(String, nullable=False)
    started_at:   Mapped[datetime]  = mapped_column(DateTime, default=datetime.utcnow)
    ended_at:     Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_s:   Mapped[int]       = mapped_column(Integer, default=0)             # seconds
    blocked_count:Mapped[int]       = mapped_column(Integer, default=0)
    block_log:    Mapped[list]      = mapped_column(JSON, default=list)             # [{type, name, ts}, ...]
    device_id:    Mapped[str | None] = mapped_column(String, nullable=True)        # which device started it

    user: Mapped["User"] = relationship("User", back_populates="sessions")


class ActiveSession(Base):
    """
    Single-row per user — the live session state that all devices poll.
    Deleted when the session stops, so /status can just check for existence.
    """
    __tablename__ = "active_sessions"

    user_id:         Mapped[str]  = mapped_column(String, ForeignKey("users.id"), primary_key=True)
    session_id:      Mapped[str]  = mapped_column(String, ForeignKey("sessions.id"), nullable=False)
    goal:            Mapped[str]  = mapped_column(Text, nullable=False)
    blocked_sites:   Mapped[list] = mapped_column(JSON, default=list)
    allowed_apps:    Mapped[list] = mapped_column(JSON, default=list)
    started_at:      Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_by:      Mapped[str | None] = mapped_column(String, nullable=True)     # device_id

    user: Mapped["User"] = relationship("User", back_populates="active_session")
