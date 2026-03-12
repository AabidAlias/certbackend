"""
app/api/auth.py
Fixed: proper DB queries, no full collection scans on login.
"""
import hashlib
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from app.utils.helpers import get_logger, utcnow

logger = get_logger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Auth"])


def get_db():
    from app.main import db
    return db


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def make_token(user_id: str) -> str:
    return hashlib.sha256(f"{user_id}-certify-secret".encode()).hexdigest()


def _safe_user(doc: dict) -> dict:
    return {
        "user_id": doc["user_id"],
        "name": doc["name"],
        "email": doc["email"],
        "org_name": doc["org_name"],
        "sender_email": doc.get("sender_email", ""),
        "has_sender_configured": bool(
            doc.get("sender_email") and doc.get("sender_app_password")
        ),
        "token": make_token(doc["user_id"]),
    }


# ── Models ─────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    org_name: str
    sender_email: str
    sender_app_password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UpdateSenderRequest(BaseModel):
    token: str
    sender_email: str
    sender_app_password: str


# ── Register ───────────────────────────────────────────────────────────────────

@router.post("/register")
async def register(req: RegisterRequest):
    db = get_db()

    existing = await db.users.find_one({"email": req.email.lower().strip()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered.")

    if not req.sender_email or not req.sender_app_password:
        raise HTTPException(status_code=400, detail="Gmail and App Password are required.")

    user_id = str(uuid.uuid4())
    doc = {
        "user_id": user_id,
        "name": req.name.strip(),
        "email": req.email.lower().strip(),
        "password_hash": hash_password(req.password),
        "org_name": req.org_name.strip(),
        "sender_email": req.sender_email.strip().lower(),
        "sender_app_password": req.sender_app_password.strip(),
        "created_at": utcnow(),
    }
    await db.users.insert_one(doc)
    logger.info(f"Registered: {req.email}")
    return _safe_user(doc)


# ── Login ──────────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(req: LoginRequest):
    db = get_db()

    # Direct query by email index — fast
    user = await db.users.find_one({"email": req.email.lower().strip()})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if user["password_hash"] != hash_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    logger.info(f"Login: {req.email}")
    return _safe_user(user)


# ── Update sender ──────────────────────────────────────────────────────────────

@router.post("/update-sender")
async def update_sender(req: UpdateSenderRequest):
    db = get_db()

    # Find user by their token — compute expected token for each user
    # More efficient: store token hash in DB
    all_users = await db.users.find(
        {}, {"user_id": 1, "email": 1}
    ).to_list(length=10000)

    matched = next(
        (u for u in all_users if make_token(u["user_id"]) == req.token), None
    )
    if not matched:
        raise HTTPException(status_code=401, detail="Invalid token.")

    await db.users.update_one(
        {"user_id": matched["user_id"]},
        {"$set": {
            "sender_email": req.sender_email.strip().lower(),
            "sender_app_password": req.sender_app_password.strip(),
        }}
    )

    # Return updated user
    updated = await db.users.find_one({"user_id": matched["user_id"]})
    logger.info(f"Sender updated: {matched['email']}")
    return _safe_user(updated)