"""
api/certificate.py
Updated: credits check before sending, deduct credits on batch start.
"""
import asyncio
import zipfile
import io
import hashlib
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Header
from fastapi.responses import StreamingResponse
import motor.motor_asyncio

from app.core.config import settings
from app.models.certificate_model import CertificateStatus
from app.services.csv_service import parse_csv
from app.services.email_service import send_certificate_email
from app.services.pdf_generator import generate_certificate_pdf
from app.utils.helpers import generate_certificate_id, get_logger, safe_delete, utcnow

logger = get_logger(__name__)
router = APIRouter(prefix="/api/certificates", tags=["Certificates"])

CHUNK_SIZE = 10
CHUNK_DELAY = 0.5


def get_db():
    from app.main import db
    return db


def get_client():
    from app.main import client
    return client


def make_token(user_id: str) -> str:
    return hashlib.sha256(f"{user_id}-certify-secret".encode()).hexdigest()


async def get_user_by_token(token: str, db) -> dict:
    all_users = await db.users.find({}).to_list(length=10000)
    user = next((u for u in all_users if make_token(u["user_id"]) == token), None)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized. Please log in again.")
    return user


# ── Template stored in MongoDB ─────────────────────────────────────────────────

async def save_template_to_db(user_id: str, file_bytes: bytes, db):
    await db.templates.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "data": file_bytes, "updated_at": utcnow()}},
        upsert=True,
    )


async def load_template_from_db(user_id: str, db) -> bytes | None:
    doc = await db.templates.find_one({"user_id": user_id})
    return doc["data"] if doc else None


async def get_template_path(user_id: str, db) -> Path:
    template_bytes = await load_template_from_db(user_id, db)
    if not template_bytes:
        if settings.TEMPLATE_PATH.exists():
            return settings.TEMPLATE_PATH
        raise HTTPException(status_code=400, detail="No certificate template found. Please upload a template first.")
    tmp_path = Path(f"/tmp/template_{user_id}.png")
    tmp_path.write_bytes(template_bytes)
    return tmp_path


# ── Upload template ────────────────────────────────────────────────────────────

@router.post("/upload-template")
async def upload_template(
    file: UploadFile = File(...),
    authorization: str = Header(default=""),
):
    if not file.filename.lower().endswith(".png"):
        raise HTTPException(status_code=400, detail="Template must be a PNG file.")
    token = authorization.replace("Bearer ", "").strip()
    db = get_db()
    user = await get_user_by_token(token, db)
    content = await file.read()
    await save_template_to_db(user["user_id"], content, db)
    logger.info(f"Template saved to DB for user: {user['email']}")
    return {"message": "Template uploaded and saved successfully."}


# ── Start batch ────────────────────────────────────────────────────────────────

@router.post("/send-batch")
async def send_batch(
    csv_file: UploadFile = File(...),
    email_subject: str = Form(...),
    email_body: str = Form(...),
    name_x_cm: float = Form(default=4.24),
    name_y_cm: float = Form(default=5.60),
    text_box_width_cm: float = Form(default=11.02),
    org_name: str = Form(default="CERT"),
    authorization: str = Header(default=""),
):
    token = authorization.replace("Bearer ", "").strip()
    db = get_db()
    user = await get_user_by_token(token, db)

    sender_email = user.get("sender_email", "")
    sender_password = user.get("sender_app_password", "")

    if not sender_email or not sender_password:
        raise HTTPException(status_code=400, detail="Please configure your Gmail sender credentials before sending.")

    template_check = await db.templates.find_one({"user_id": user["user_id"]})
    if not template_check and not settings.TEMPLATE_PATH.exists():
        raise HTTPException(status_code=400, detail="Please upload a certificate template first.")

    if not csv_file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Must be a CSV file.")

    csv_bytes = await csv_file.read()
    try:
        rows = parse_csv(csv_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not rows:
        raise HTTPException(status_code=400, detail="CSV has no valid rows.")

    # ✅ CREDITS CHECK
    user_credits = user.get("credits", 0)
    required = len(rows)
    if user_credits < required:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits. You need {required} credits but have {user_credits}. Please purchase more."
        )

    # ✅ DEDUCT CREDITS before processing
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$inc": {"credits": -required}}
    )

    batch_id = generate_certificate_id()
    year = datetime.utcnow().year

    docs = []
    for name, email in rows:
        cert_id = generate_certificate_id()
        short_id = cert_id.replace("-", "").upper()[:5]
        cert_number = f"{org_name.strip().replace(' ', '-').upper()}-{year}-{short_id}"
        docs.append({
            "certificate_id": cert_id,
            "cert_number": cert_number,
            "batch_id": batch_id,
            "user_id": user["user_id"],
            "name": name,
            "email": email,
            "org_name": org_name,
            "status": CertificateStatus.PENDING,
            "file_path": None,
            "error_message": None,
            "created_at": utcnow(),
        })

    await db.certificates.insert_many(docs)
    logger.info(f"Batch {batch_id}: {len(docs)} records | from: {sender_email} | credits deducted: {required}")

    asyncio.create_task(_process_batch(
        batch_id=batch_id,
        user_id=user["user_id"],
        email_subject=email_subject,
        email_body=email_body,
        name_x_cm=name_x_cm,
        name_y_cm=name_y_cm,
        text_box_width_cm=text_box_width_cm,
        sender_email=sender_email,
        sender_password=sender_password,
        db=db,
    ))

    return {"batch_id": batch_id, "total": len(docs), "sender": sender_email}


# ── Batch processor ────────────────────────────────────────────────────────────

async def _process_batch(
    batch_id, user_id, email_subject, email_body,
    name_x_cm, name_y_cm, text_box_width_cm,
    sender_email, sender_password, db
):
    try:
        template_path = await get_template_path(user_id, db)
    except Exception as e:
        logger.error(f"[{batch_id}] Cannot load template: {e}")
        await db.certificates.update_many(
            {"batch_id": batch_id},
            {"$set": {"status": CertificateStatus.FAILED, "error_message": "Template not found"}},
        )
        return

    all_docs = await db.certificates.find(
        {"batch_id": batch_id, "status": CertificateStatus.PENDING}
    ).to_list(length=10000)

    total = len(all_docs)
    logger.info(f"[{batch_id}] Processing {total} recipients | from: {sender_email}")

    for i in range(0, total, CHUNK_SIZE):
        chunk = all_docs[i: i + CHUNK_SIZE]
        await asyncio.gather(*[
            _process_single(
                doc, batch_id, email_subject, email_body,
                name_x_cm, name_y_cm, text_box_width_cm,
                str(template_path), sender_email, sender_password, db
            )
            for doc in chunk
        ])
        logger.info(f"[{batch_id}] {min(i + CHUNK_SIZE, total)}/{total}")
        if i + CHUNK_SIZE < total:
            await asyncio.sleep(CHUNK_DELAY)

    logger.info(f"[{batch_id}] Complete!")


async def _process_single(
    doc, batch_id, email_subject, email_body,
    name_x_cm, name_y_cm, text_box_width_cm,
    template_path, sender_email, sender_password, db
):
    cert_id = doc["certificate_id"]
    name = doc["name"]
    email = doc["email"]
    cert_number = doc.get("cert_number", cert_id[:8].upper())
    pdf_path = Path(f"/tmp/{cert_id}.pdf")

    try:
        generate_certificate_pdf(
            name=name, certificate_id=cert_id, cert_number=cert_number,
            output_path=pdf_path, name_x_cm=name_x_cm, name_y_cm=name_y_cm,
            text_box_width_cm=text_box_width_cm, template_path=template_path,
        )
        await send_certificate_email(
            recipient_name=name, recipient_email=email,
            subject_template=email_subject, body_template=email_body,
            pdf_path=pdf_path, sender_email=sender_email,
            sender_app_password=sender_password,
        )
        await db.certificates.update_one(
            {"certificate_id": cert_id},
            {"$set": {"status": CertificateStatus.SENT}},
        )
        logger.info(f"[{batch_id}] ✅ {name} → {email}")
    except Exception as e:
        logger.error(f"[{batch_id}] ❌ {name}: {e}")
        await db.certificates.update_one(
            {"certificate_id": cert_id},
            {"$set": {"status": CertificateStatus.FAILED, "error_message": str(e)}},
        )
    finally:
        safe_delete(pdf_path)


# ── Progress ───────────────────────────────────────────────────────────────────

@router.get("/progress/{batch_id}")
async def get_progress(batch_id: str):
    db = get_db()
    total   = await db.certificates.count_documents({"batch_id": batch_id})
    sent    = await db.certificates.count_documents({"batch_id": batch_id, "status": CertificateStatus.SENT})
    failed  = await db.certificates.count_documents({"batch_id": batch_id, "status": CertificateStatus.FAILED})
    pending = total - sent - failed
    return {
        "batch_id": batch_id, "total": total, "sent": sent,
        "failed": failed, "pending": pending,
        "done": pending == 0 and total > 0,
    }


# ── Status ─────────────────────────────────────────────────────────────────────

@router.get("/status/{batch_id}")
async def get_status(batch_id: str, skip: int = 0, limit: int = 10000):
    db = get_db()
    cursor = db.certificates.find(
        {"batch_id": batch_id},
        {"_id": 0, "certificate_id": 1, "cert_number": 1, "name": 1,
         "email": 1, "status": 1, "error_message": 1, "created_at": 1},
    ).skip(skip).limit(limit)
    records = await cursor.to_list(length=limit)
    return {"records": records}


# ── Verify (PUBLIC) ────────────────────────────────────────────────────────────

@router.get("/verify/{cert_number}")
async def verify_certificate(cert_number: str):
    db = get_db()
    doc = await db.certificates.find_one(
        {
            "cert_number": {"$regex": f"^{cert_number.strip()}$", "$options": "i"},
            "status": CertificateStatus.SENT
        },
        {"_id": 0, "name": 1, "cert_number": 1, "org_name": 1, "created_at": 1}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Certificate not found or not valid.")
    return doc


# ── Retry ──────────────────────────────────────────────────────────────────────

@router.post("/retry/{batch_id}")
async def retry_failed(
    batch_id: str,
    email_subject: str = Form(...),
    email_body: str = Form(...),
    authorization: str = Header(default=""),
):
    token = authorization.replace("Bearer ", "").strip()
    db = get_db()
    user = await get_user_by_token(token, db)

    result = await db.certificates.update_many(
        {"batch_id": batch_id, "status": CertificateStatus.FAILED},
        {"$set": {"status": CertificateStatus.PENDING, "error_message": None}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="No failed records.")

    asyncio.create_task(_process_batch(
        batch_id=batch_id,
        user_id=user["user_id"],
        email_subject=email_subject,
        email_body=email_body,
        name_x_cm=settings.NAME_X_CM,
        name_y_cm=settings.NAME_Y_CM,
        text_box_width_cm=settings.TEXT_BOX_WIDTH_CM,
        sender_email=user.get("sender_email", ""),
        sender_password=user.get("sender_app_password", ""),
        db=db,
    ))
    return {"message": f"Retrying {result.modified_count} records."}


# ── Download ZIP ───────────────────────────────────────────────────────────────

@router.get("/download-zip/{batch_id}")
async def download_zip(batch_id: str):
    db = get_db()
    records = await db.certificates.find({"batch_id": batch_id}).to_list(length=10000)
    if not records:
        raise HTTPException(status_code=404, detail="Batch not found.")

    user_id = records[0].get("user_id", "")
    try:
        template_path = await get_template_path(user_id, db)
    except:
        template_path = settings.TEMPLATE_PATH

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc in records:
            name = doc["name"]
            cert_id = doc["certificate_id"]
            cert_number = doc.get("cert_number", cert_id[:8])
            pdf_path = Path(f"/tmp/{cert_id}_dl.pdf")
            try:
                generate_certificate_pdf(
                    name=name, certificate_id=cert_id, cert_number=cert_number,
                    output_path=pdf_path, template_path=str(template_path),
                    name_x_cm=settings.NAME_X_CM, name_y_cm=settings.NAME_Y_CM,
                    text_box_width_cm=settings.TEXT_BOX_WIDTH_CM,
                )
                zf.write(pdf_path, arcname=f"{name.replace(' ', '_')}_certificate.pdf")
            except Exception as e:
                logger.warning(f"Skipped {name}: {e}")
            finally:
                safe_delete(pdf_path)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=certificates_{batch_id[:8]}.zip"},
    )
