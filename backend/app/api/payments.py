"""
api/payments.py
Razorpay payment integration using direct HTTP API (no razorpay SDK).
The razorpay package is incompatible with Python 3.13 on Railway.
"""
import base64
import hashlib
import hmac
import os
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from app.utils.helpers import get_logger, utcnow
from app.services.invoice_service import send_invoice_email

logger = get_logger(__name__)
router = APIRouter(prefix="/api/payments", tags=["Payments"])

PRICE_PER_EMAIL = 3.4
MIN_EMAILS = 35
RAZORPAY_API = "https://api.razorpay.com/v1"


def get_db():
    from app.main import db
    return db


def make_token(user_id: str) -> str:
    return hashlib.sha256(f"{user_id}-certify-secret".encode()).hexdigest()


async def get_user_by_token(token: str, db) -> dict:
    all_users = await db.users.find({}).to_list(length=10000)
    user = next((u for u in all_users if make_token(u["user_id"]) == token), None)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized. Please log in again.")
    return user


def get_auth_header():
    key_id     = os.environ.get("RAZORPAY_KEY_ID", "")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
    if not key_id or not key_secret:
        raise HTTPException(status_code=500, detail="Payment system not configured.")
    credentials = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    return {"Authorization": f"Basic {credentials}", "Content-Type": "application/json"}


# ── Models ─────────────────────────────────────────────────────────────────────

class CreateOrderRequest(BaseModel):
    email_count: int


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


# ── Create Order ───────────────────────────────────────────────────────────────

@router.post("/create-order")
async def create_order(
    req: CreateOrderRequest,
    authorization: str = Header(default=""),
):
    token = authorization.replace("Bearer ", "").strip()
    db = get_db()
    user = await get_user_by_token(token, db)

    if req.email_count < MIN_EMAILS:
        raise HTTPException(status_code=400, detail=f"Minimum purchase is {MIN_EMAILS} emails.")

    amount_inr   = round(req.email_count * PRICE_PER_EMAIL, 2)
    amount_paise = int(amount_inr * 100)

    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": f"order_{uuid.uuid4().hex[:8]}",
        "notes": {"user_id": user["user_id"], "email_count": req.email_count},
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{RAZORPAY_API}/orders",
            json=payload,
            headers=get_auth_header(),
        )

    if response.status_code != 200:
        logger.error(f"Razorpay order error: {response.text}")
        raise HTTPException(status_code=502, detail="Failed to create payment order.")

    order = response.json()

    await db.orders.insert_one({
        "order_id": order["id"],
        "user_id": user["user_id"],
        "email_count": req.email_count,
        "amount_inr": amount_inr,
        "status": "pending",
        "created_at": utcnow(),
    })

    logger.info(f"Order created: {order['id']} | {req.email_count} emails | Rs.{amount_inr}")
    return {
        "order_id": order["id"],
        "amount": amount_paise,
        "currency": "INR",
        "email_count": req.email_count,
        "amount_inr": amount_inr,
        "key_id": os.environ.get("RAZORPAY_KEY_ID", ""),
    }


# ── Verify Payment ─────────────────────────────────────────────────────────────

@router.post("/verify")
async def verify_payment(
    req: VerifyPaymentRequest,
    authorization: str = Header(default=""),
):
    token = authorization.replace("Bearer ", "").strip()
    db = get_db()
    user = await get_user_by_token(token, db)

    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
    if not key_secret:
        raise HTTPException(status_code=500, detail="Payment system not configured.")

    # Verify signature
    body     = f"{req.razorpay_order_id}|{req.razorpay_payment_id}"
    expected = hmac.new(key_secret.encode(), body.encode(), hashlib.sha256).hexdigest()

    if expected != req.razorpay_signature:
        raise HTTPException(status_code=400, detail="Payment verification failed.")

    order_doc = await db.orders.find_one({"order_id": req.razorpay_order_id})
    if not order_doc:
        raise HTTPException(status_code=404, detail="Order not found.")

    if order_doc["status"] == "paid":
        raise HTTPException(status_code=400, detail="Order already processed.")

    email_count = order_doc["email_count"]
    paid_at     = utcnow()

    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$inc": {"credits": email_count}}
    )

    invoice_number = f"GC-{paid_at.strftime('%Y%m%d')}-{req.razorpay_order_id[-6:].upper()}"

    await db.orders.update_one(
        {"order_id": req.razorpay_order_id},
        {"$set": {
            "status": "paid",
            "payment_id": req.razorpay_payment_id,
            "invoice_number": invoice_number,
            "paid_at": paid_at,
        }}
    )

    updated_user = await db.users.find_one({"user_id": user["user_id"]})
    credits = updated_user.get("credits", 0)

    try:
        await send_invoice_email(
            customer_name=user["name"],
            customer_email=user["email"],
            invoice_number=invoice_number,
            email_count=email_count,
            amount_inr=order_doc["amount_inr"],
            payment_id=req.razorpay_payment_id,
            order_id=req.razorpay_order_id,
            paid_at=paid_at,
        )
    except Exception as e:
        logger.error(f"Invoice email failed (non-critical): {e}")

    logger.info(f"Payment verified: {req.razorpay_payment_id} | +{email_count} credits")
    return {
        "success": True,
        "credits_added": email_count,
        "total_credits": credits,
        "invoice_number": invoice_number,
    }


# ── Get Credits ────────────────────────────────────────────────────────────────

@router.get("/credits")
async def get_credits(authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "").strip()
    db = get_db()
    user = await get_user_by_token(token, db)
    return {"credits": user.get("credits", 0)}
