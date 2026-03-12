"""
services/email_service.py
Sends certificate emails using Brevo HTTP API (not SMTP).
HTTP API works on Railway — SMTP ports are blocked.
"""
import base64
import os
from pathlib import Path

import httpx

from app.utils.helpers import get_logger, replace_template_vars

logger = get_logger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


async def send_certificate_email(
    recipient_name: str,
    recipient_email: str,
    subject_template: str,
    body_template: str,
    pdf_path: str | Path,
    sender_email: str,        # user's Gmail — used as Reply-To
    sender_app_password: str, # not used, kept for compatibility
) -> None:
    subject  = replace_template_vars(subject_template, recipient_name)
    body     = replace_template_vars(body_template, recipient_name)
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    brevo_api_key      = os.environ.get("BREVO_API_KEY", "")
    brevo_sender_email = os.environ.get("BREVO_SENDER_EMAIL", "")
    brevo_sender_name  = os.environ.get("BREVO_SENDER_NAME", "GenCirty")

    if not brevo_api_key:
        raise ValueError("BREVO_API_KEY not configured in environment.")
    if not brevo_sender_email:
        raise ValueError("BREVO_SENDER_EMAIL not configured in environment.")

    # Encode PDF as base64
    with open(pdf_path, "rb") as f:
        pdf_b64 = base64.b64encode(f.read()).decode("utf-8")

    filename = f"certificate_{recipient_name.replace(' ', '_')}.pdf"

    payload = {
        "sender": {
            "name": brevo_sender_name,
            "email": brevo_sender_email,
        },
        "replyTo": {
            "email": sender_email,
            "name": recipient_name,
        },
        "to": [{"email": recipient_email, "name": recipient_name}],
        "subject": subject,
        "textContent": body,
        "attachment": [
            {
                "name": filename,
                "content": pdf_b64,
            }
        ],
    }

    headers = {
        "api-key": brevo_api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(BREVO_API_URL, json=payload, headers=headers)

    if response.status_code not in (200, 201):
        raise RuntimeError(f"Brevo API error {response.status_code}: {response.text}")

    logger.info(f"✅ Email sent via Brevo API to {recipient_email}")
