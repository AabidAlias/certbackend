"""
services/email_service.py
Sends certificate emails using the USER's own Gmail credentials.
Uses port 465 with SSL (port 587 is blocked on Railway).
"""
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiosmtplib

from app.utils.helpers import get_logger, replace_template_vars

logger = get_logger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL port — 587 is blocked on Railway


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

    if not sender_email or not sender_app_password:
        raise ValueError("Sender Gmail credentials are not configured.")

    # Build MIME message
    message = MIMEMultipart()
    message["From"]    = sender_email
    message["To"]      = recipient_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    # Attach PDF
    with open(pdf_path, "rb") as f:
        part = MIMEApplication(f.read(), _subtype="pdf")
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=f"certificate_{recipient_name.replace(' ', '_')}.pdf",
        )
        message.attach(part)

    # Send via port 465 SSL (not STARTTLS)
    await aiosmtplib.send(
        message,
        hostname=SMTP_HOST,
        port=SMTP_PORT,
        username=sender_email,
        password=sender_app_password,
        use_tls=True,      # SSL from the start
        start_tls=False,   # Do NOT use STARTTLS on port 465
    )
    logger.info(f"✅ Email sent from {sender_email} to {recipient_email}")