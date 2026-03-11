"""
app/api/auth.py
User registration and login.
Each user stores their own Gmail + App Password for sending certificates.
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
    """Return user dict without sensitive fields."""
    return {
        "user_id": doc["user_id"],
        "name": doc["name"],
        "email": doc["email"],
        "org_name": doc["org_name"],
        "sender_email": doc.get("sender_email", ""),
        # Never return app password to frontend
        "has_sender_configured": bool(doc.get("sender_email") and doc.get("sender_app_password")),
        "token": make_token(doc["user_id"]),
    }


# ── Models ─────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    org_name: str
    sender_email: str        # Gmail they want to send FROM
    sender_app_password: str # Gmail App Password
    # Consent flags captured during registration (stored for compliance).
    # Defaults avoid 422 if older clients don't send these; we enforce in route logic.
    agree_terms: bool = False
    agree_data: bool = False
    agree_password: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UpdateSenderRequest(BaseModel):
    token: str
    sender_email: str
    sender_app_password: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/register")
async def register(req: RegisterRequest):
    db = get_db()

    existing = await db.users.find_one({"email": req.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered.")

    if not req.sender_email or not req.sender_app_password:
        raise HTTPException(status_code=400, detail="Sender Gmail and App Password are required.")

    if not (req.agree_terms and req.agree_data and req.agree_password):
        raise HTTPException(status_code=400, detail="All consent checkboxes are required to proceed.")

    user_id = str(uuid.uuid4())
    now = utcnow()
    doc = {
        "user_id": user_id,
        "name": req.name.strip(),
        "email": req.email.lower().strip(),
        "password_hash": hash_password(req.password),
        "org_name": req.org_name.strip(),
        "sender_email": req.sender_email.strip().lower(),
        "sender_app_password": req.sender_app_password.strip(),  # stored as-is (consider encrypting in production)
        "consents": {
            "terms": {"agreed": True, "agreed_at": now},
            "data": {"agreed": True, "agreed_at": now},
            "app_password": {"agreed": True, "agreed_at": now},
        },
        "created_at": now,
    }
    await db.users.insert_one(doc)
    logger.info(f"Registered: {req.email} | sender: {req.sender_email}")
    return _safe_user(doc)


@router.post("/login")
async def login(req: LoginRequest):
    db = get_db()

    user = await db.users.find_one({"email": req.email.lower()})
    if not user or user["password_hash"] != hash_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    logger.info(f"Login: {req.email}")
    return _safe_user(user)


@router.post("/update-sender")
async def update_sender(req: UpdateSenderRequest):
    """Allow user to update their sender Gmail credentials."""
    db = get_db()

    user = await db.users.find_one({"token": req.token})
    # Find by token
    all_users = await db.users.find({}).to_list(length=10000)
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
    logger.info(f"Sender updated for user: {matched['email']}")
    return {"message": "Sender email updated successfully."}
