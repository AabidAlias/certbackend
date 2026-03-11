"""
services/email_service.py
Sends certificate emails using the USER's own Gmail credentials.
Each user provides their own Gmail + App Password — not a shared account.
"""
import base64
import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiosmtplib

from app.utils.helpers import get_logger, replace_template_vars

logger = get_logger(__name__)

SMTP_HOST = "smtp.gmail.com"
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
    """
    Send a certificate email using the user's own Gmail credentials.

    Args:
        recipient_name: Full name of the recipient
        recipient_email: Recipient email address
        subject_template: Subject with optional {{name}}
        body_template: Body with optional {{name}}
        pdf_path: Path to the generated PDF
        sender_email: User's Gmail address (sends FROM this)
        sender_app_password: User's Gmail App Password
    """
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

    # Send via user's Gmail SMTP
    await aiosmtplib.send(
        message,
        hostname=SMTP_HOST,
        port=SMTP_PORT,
        username=sender_email,
        password=sender_app_password,
        start_tls=True,
    )
    logger.info(f"Email sent from {sender_email} to {recipient_email}")
