import os
import stripe
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.auth import current_user
from app.models import User

router = APIRouter()

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET  = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PRICE_MONTHLY  = os.environ.get("STRIPE_PRICE_MONTHLY", "")
PRICE_YEARLY   = os.environ.get("STRIPE_PRICE_YEARLY", "")
PRICE_LIFETIME = os.environ.get("STRIPE_PRICE_LIFETIME", "")
APP_URL         = os.environ.get("APP_URL", "https://backend-production-b2cc.up.railway.app")


# ── Schemas ───────────────────────────────────────────────────────────────────
class CheckoutRequest(BaseModel):
    plan: str   # "monthly" or "yearly"

class CheckoutResponse(BaseModel):
    checkout_url: str

class PortalResponse(BaseModel):
    portal_url: str


# ── Helper: get or create Stripe customer ─────────────────────────────────────
async def _get_or_create_customer(user: User, db: AsyncSession) -> str:
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = stripe.Customer.create(
        email=user.email,
        name=user.display_name or "",
        metadata={"user_id": user.id},
    )
    user.stripe_customer_id = customer.id
    await db.commit()
    return customer.id


# ── POST /billing/checkout ────────────────────────────────────────────────────
@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    user: User = Depends(current_user),
    db:   AsyncSession = Depends(get_db),
):
    if body.plan not in ("monthly", "yearly", "lifetime"):
        raise HTTPException(status_code=400, detail="plan must be monthly, yearly, or lifetime")

    price_id = {
        "monthly":  PRICE_MONTHLY,
        "yearly":   PRICE_YEARLY,
        "lifetime": PRICE_LIFETIME,
    }[body.plan]

    if not price_id:
        raise HTTPException(status_code=500, detail="Stripe prices not configured")

    customer_id = await _get_or_create_customer(user, db)
    is_lifetime = body.plan == "lifetime"

    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        # KEY DIFFERENCE: lifetime is "payment" mode, not "subscription"
        mode="payment" if is_lifetime else "subscription",
        success_url=f"{APP_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{APP_URL}/billing/cancel",
        metadata={"user_id": user.id, "plan": body.plan},
        # Trial carry-over only applies to recurring plans
        **({"subscription_data": {"trial_period_days": _remaining_trial_days(user)}}
           if not is_lifetime and _remaining_trial_days(user) > 0 else {}),
        allow_promotion_codes=True,
    )
    return CheckoutResponse(checkout_url=session.url)

def _remaining_trial_days(user: User) -> int:
    if not user.trial_ends_at:
        return 0
    delta = user.trial_ends_at - datetime.utcnow()
    return max(0, delta.days)


# ── GET /billing/portal ───────────────────────────────────────────────────────
@router.get("/portal", response_model=PortalResponse)
async def billing_portal(
    user: User = Depends(current_user),
    db:   AsyncSession = Depends(get_db),
):
    """
    Returns a Stripe Customer Portal URL so users can manage or cancel
    their subscription without you building any billing UI.
    """
    if not user.stripe_customer_id:
        raise HTTPException(status_code=404, detail="No billing account found")
    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{APP_URL}/billing/portal-return",
    )
    return PortalResponse(portal_url=session.url)


# ── GET /billing/success & /cancel — browser landing pages ───────────────────
@router.get("/success")
async def checkout_success():
    """Simple HTML page shown in the browser after successful payment."""
    return _html_page(
        "Payment successful",
        "✓",
        "You're now on Nothing Alternative Premium.",
        "Return to the app — your access has been upgraded.",
        "#00e676",
    )

@router.get("/cancel")
async def checkout_cancel():
    return _html_page(
        "Checkout cancelled",
        "×",
        "No charge was made.",
        "Return to the app whenever you're ready to upgrade.",
        "#8888aa",
    )

@router.get("/portal-return")
async def portal_return():
    return _html_page(
        "Billing updated",
        "✓",
        "Your billing settings have been saved.",
        "Return to the app.",
        "#3a3aff",
    )

def _html_page(title, icon, heading, sub, color):
    from fastapi.responses import HTMLResponse
    return HTMLResponse(f"""<!doctype html><html><head>
<meta charset="utf-8"><title>{title}</title>
<style>
  body{{margin:0;display:flex;align-items:center;justify-content:center;
       min-height:100vh;background:#0e0e0f;font-family:system-ui,sans-serif;color:#fff}}
  .box{{text-align:center;max-width:340px}}
  .icon{{font-size:52px;color:{color};margin-bottom:16px}}
  h2{{margin:0 0 8px;font-size:22px}}
  p{{color:#8888aa;font-size:14px;margin:0}}
</style></head><body>
<div class="box">
  <div class="icon">{icon}</div>
  <h2>{heading}</h2><p>{sub}</p>
</div></body></html>""")


# ── POST /billing/webhook — Stripe event handler ──────────────────────────────
@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
):
    """
    Stripe calls this endpoint for every subscription lifecycle event.
    This is the single source of truth for subscription status — never
    trust the client to report its own subscription state.
    """
    body = await request.body()

    try:
        event = stripe.Webhook.construct_event(body, stripe_signature, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    await _handle_stripe_event(event, db)
    return {"received": True}


async def _handle_stripe_event(event: dict, db: AsyncSession):
    event_type = event["type"]
    obj        = event["data"]["object"]

    # ── Lifetime purchase (one-time payment) ──────────────────────────────────
    if event_type == "checkout.session.completed":
        if obj.get("mode") == "payment" and obj.get("metadata", {}).get("plan") == "lifetime":
            customer_id = obj.get("customer")
            if not customer_id:
                return
            result = await db.execute(
                select(User).where(User.stripe_customer_id == customer_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.subscription_status    = "lifetime"
                user.stripe_subscription_id = None   # no subscription ID for one-time
                user.current_period_end     = None   # never expires
                await db.commit()
        return  # don't fall through to subscription logic

    # ── Subscription events ───────────────────────────────────────────────────
    customer_id = obj.get("customer")
    if not customer_id:
        return

    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return

    # Never downgrade a lifetime user via subscription events
    if user.subscription_status == "lifetime":
        return

    if event_type == "customer.subscription.created":
        _apply_subscription(user, obj)
    elif event_type == "customer.subscription.updated":
        _apply_subscription(user, obj)
    elif event_type == "customer.subscription.deleted":
        user.subscription_status    = "cancelled"
        user.stripe_subscription_id = None
        user.current_period_end     = None
    elif event_type == "invoice.payment_succeeded":
        if user.subscription_status in ("past_due", "cancelled"):
            user.subscription_status = "active"
    elif event_type == "invoice.payment_failed":
        user.subscription_status = "past_due"

    await db.commit()


def _apply_subscription(user: User, subscription: dict):
    """Maps a Stripe subscription object onto the User model."""
    status_map = {
        "active":   "active",
        "trialing": "active",   # Stripe trial = we consider active
        "past_due": "past_due",
        "canceled": "cancelled",
        "unpaid":   "past_due",
        "incomplete": "past_due",
        "incomplete_expired": "expired",
    }
    stripe_status = subscription.get("status", "")
    user.subscription_status    = status_map.get(stripe_status, "free")
    user.stripe_subscription_id = subscription.get("id")
    period_end = subscription.get("current_period_end")
    if period_end:
        user.current_period_end = datetime.utcfromtimestamp(period_end)