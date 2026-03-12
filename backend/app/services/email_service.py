"""
services/email_service.py
Sends certificate emails using Brevo SMTP.
Brevo works on Railway (unlike Gmail SMTP which is blocked).
The user's Gmail is set as Reply-To so recipients can reply to them directly.
"""
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
import os

import aiosmtplib

from app.utils.helpers import get_logger, replace_template_vars

logger = get_logger(__name__)

SMTP_HOST = "smtp-relay.brevo.com"
SMTP_PORT = 587


async def send_certificate_email(
    recipient_name: str,
    recipient_email: str,
    subject_template: str,
    body_template: str,
    pdf_path: str | Path,
    sender_email: str,
    sender_app_password: str,
) -> None:
    subject = replace_template_vars(subject_template, recipient_name)
    body    = replace_template_vars(body_template, recipient_name)
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    brevo_user         = os.environ.get("BREVO_SMTP_USER", "")
    brevo_password     = os.environ.get("BREVO_SMTP_PASSWORD", "")
    brevo_sender_email = os.environ.get("BREVO_SENDER_EMAIL", brevo_user)
    brevo_sender_name  = os.environ.get("BREVO_SENDER_NAME", "GenCirty")

    if not brevo_user or not brevo_password:
        raise ValueError("Brevo SMTP credentials not configured in environment.")

    message = MIMEMultipart()
    message["From"]     = f"{brevo_sender_name} <{brevo_sender_email}>"
    message["To"]       = recipient_email
    message["Subject"]  = subject
    message["Reply-To"] = sender_email

    message.attach(MIMEText(body, "plain"))

    with open(pdf_path, "rb") as f:
        part = MIMEApplication(f.read(), _subtype="pdf")
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=f"certificate_{recipient_name.replace(' ', '_')}.pdf",
        )
        message.attach(part)

    await aiosmtplib.send(
        message,
        hostname=SMTP_HOST,
        port=SMTP_PORT,
        username=brevo_user,
        password=brevo_password,
        start_tls=True,
    )
    logger.info(f"✅ Email sent via Brevo to {recipient_email} (reply-to: {sender_email})")