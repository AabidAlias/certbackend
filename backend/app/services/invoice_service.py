"""
services/invoice_service.py
Generates a detailed PDF invoice and sends it to the customer via Brevo.
Triggered after successful Razorpay payment verification.
"""
import base64
import io
import os
from datetime import datetime
from pathlib import Path

import httpx
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT

from app.utils.helpers import get_logger

logger = get_logger(__name__)

PRICE_PER_EMAIL = 3.4  # update this if you change price
GST_RATE        = 0.18
BREVO_API_URL   = "https://api.brevo.com/v3/smtp/email"
INVOICE_FROM_EMAIL = "gencirty01@gmail.com"
INVOICE_FROM_NAME  = "GenCirty"


def generate_invoice_pdf(
    invoice_number: str,
    customer_name: str,
    customer_email: str,
    email_count: int,
    amount_inr: float,
    payment_id: str,
    order_id: str,
    paid_at: datetime,
) -> bytes:
    """Generate a detailed invoice PDF and return as bytes."""

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()
    story  = []

    # ── Custom styles ──────────────────────────────────────────────────────────
    red       = colors.HexColor("#dc2626")
    dark_gray = colors.HexColor("#1f2937")
    mid_gray  = colors.HexColor("#6b7280")
    light_bg  = colors.HexColor("#fef2f2")

    title_style = ParagraphStyle("title", fontSize=28, textColor=red, fontName="Helvetica-Bold", spaceAfter=4)
    sub_style   = ParagraphStyle("sub",   fontSize=10, textColor=mid_gray, fontName="Helvetica")
    head_style  = ParagraphStyle("head",  fontSize=11, textColor=dark_gray, fontName="Helvetica-Bold")
    body_style  = ParagraphStyle("body",  fontSize=10, textColor=dark_gray, fontName="Helvetica")
    right_style = ParagraphStyle("right", fontSize=10, textColor=dark_gray, fontName="Helvetica", alignment=TA_RIGHT)
    total_style = ParagraphStyle("total", fontSize=14, textColor=red, fontName="Helvetica-Bold", alignment=TA_RIGHT)

    # ── Header ─────────────────────────────────────────────────────────────────
    header_data = [[
        Paragraph("<b>GenCirty</b>", ParagraphStyle("logo", fontSize=22, textColor=red, fontName="Helvetica-Bold")),
        Paragraph(f"<b>INVOICE</b><br/><font color='grey' size='10'>#{invoice_number}</font>",
                  ParagraphStyle("inv", fontSize=18, textColor=dark_gray, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
    ]]
    header_table = Table(header_data, colWidths=[9*cm, 8*cm])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=2, color=red, spaceAfter=16))

    # ── Company & Invoice details side by side ─────────────────────────────────
    date_str = paid_at.strftime("%d %B %Y")
    time_str = paid_at.strftime("%I:%M %p")

    details_data = [[
        # Left: company info
        Paragraph(
            "<b>From</b><br/>GenCirty<br/>Certificate Automation Platform<br/>gencirty01@gmail.com<br/>gencirty.vercel.app",
            body_style
        ),
        # Right: invoice meta
        Paragraph(
            f"<b>Invoice Date:</b> {date_str}<br/>"
            f"<b>Time:</b> {time_str}<br/>"
            f"<b>Payment ID:</b> {payment_id}<br/>"
            f"<b>Order ID:</b> {order_id}<br/>"
            f"<b>Status:</b> <font color='green'>PAID</font>",
            ParagraphStyle("meta", fontSize=10, textColor=dark_gray, fontName="Helvetica", alignment=TA_RIGHT)
        ),
    ]]
    details_table = Table(details_data, colWidths=[9*cm, 8*cm])
    details_table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 20))

    # ── Bill To ────────────────────────────────────────────────────────────────
    story.append(Paragraph("<b>Bill To</b>", head_style))
    story.append(Spacer(1, 4))
    bill_data = [[
        Paragraph(f"{customer_name}<br/>{customer_email}", body_style)
    ]]
    bill_table = Table(bill_data, colWidths=[17*cm])
    bill_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), light_bg),
        ("ROUNDEDCORNERS", [6]),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (-1,-1), 12),
    ]))
    story.append(bill_table)
    story.append(Spacer(1, 20))

    # ── Items table ────────────────────────────────────────────────────────────
    story.append(Paragraph("<b>Order Details</b>", head_style))
    story.append(Spacer(1, 8))

    subtotal   = round(email_count * PRICE_PER_EMAIL, 2)
    gst_amount = round(subtotal * GST_RATE, 2)
    total      = round(subtotal + gst_amount, 2)

    items_data = [
        # Header row
        [
            Paragraph("<b>Description</b>", ParagraphStyle("th", fontSize=10, textColor=colors.white, fontName="Helvetica-Bold")),
            Paragraph("<b>Qty</b>",         ParagraphStyle("th", fontSize=10, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_CENTER)),
            Paragraph("<b>Unit Price</b>",  ParagraphStyle("th", fontSize=10, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
            Paragraph("<b>Amount</b>",      ParagraphStyle("th", fontSize=10, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
        ],
        # Item row
        [
            Paragraph("Certificate Email Credits<br/><font size='8' color='grey'>Bulk email sending for digital certificates</font>", body_style),
            Paragraph(str(email_count), ParagraphStyle("td_c", fontSize=10, fontName="Helvetica", alignment=TA_CENTER)),
            Paragraph(f"Rs.{PRICE_PER_EMAIL:.2f}", right_style),
            Paragraph(f"Rs.{subtotal:.2f}", right_style),
        ],
    ]

    items_table = Table(items_data, colWidths=[8*cm, 2.5*cm, 3*cm, 3.5*cm])
    items_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), red),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, colors.HexColor("#f9fafb")]),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#e5e7eb")),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 12))

    # ── Totals ─────────────────────────────────────────────────────────────────
    totals_data = [
        ["Subtotal",       f"Rs.{subtotal:.2f}"],
        [f"GST (18%)",     f"Rs.{gst_amount:.2f}"],
        ["Total Paid",     f"Rs.{total:.2f}"],
    ]
    totals_table = Table(
        [[Paragraph(r, ParagraphStyle("tl", fontSize=10, fontName="Helvetica" if i<2 else "Helvetica-Bold", alignment=TA_RIGHT)),
          Paragraph(v, ParagraphStyle("tv", fontSize=10, fontName="Helvetica" if i<2 else "Helvetica-Bold", textColor=red if i==2 else dark_gray, alignment=TA_RIGHT))]
         for i,(r,v) in enumerate(totals_data)],
        colWidths=[13*cm, 4*cm]
    )
    totals_table.setStyle(TableStyle([
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LINEABOVE",     (0,2), (-1,2), 1.5, red),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 30))

    # ── Footer ─────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb"), spaceAfter=12))
    story.append(Paragraph(
        "Thank you for using GenCirty! Your credits have been added to your account.<br/>"
        "<font color='grey'>For support: gencirty01@gmail.com | gencirty.vercel.app</font>",
        ParagraphStyle("footer", fontSize=9, textColor=dark_gray, fontName="Helvetica", alignment=TA_CENTER)
    ))

    doc.build(story)
    return buffer.getvalue()


async def send_invoice_email(
    customer_name: str,
    customer_email: str,
    invoice_number: str,
    email_count: int,
    amount_inr: float,
    payment_id: str,
    order_id: str,
    paid_at: datetime,
) -> None:
    """Send invoice PDF to customer via Brevo API."""

    pdf_bytes = generate_invoice_pdf(
        invoice_number=invoice_number,
        customer_name=customer_name,
        customer_email=customer_email,
        email_count=email_count,
        amount_inr=amount_inr,
        payment_id=payment_id,
        order_id=order_id,
        paid_at=paid_at,
    )

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    subtotal   = round(email_count * PRICE_PER_EMAIL, 2)
    gst_amount = round(subtotal * GST_RATE, 2)
    total      = round(subtotal + gst_amount, 2)

    body = (
        f"Dear {customer_name},\n\n"
        f"Thank you for your payment! Your invoice is attached.\n\n"
        f"Summary:\n"
        f"  Credits purchased: {email_count} emails\n"
        f"  Amount paid: Rs.{total:.2f}\n"
        f"  Payment ID: {payment_id}\n\n"
        f"Your credits have been added to your GenCirty account.\n\n"
        f"Best regards,\nGenCirty Team\ngencirty.vercel.app"
    )

    payload = {
        "sender": {"name": INVOICE_FROM_NAME, "email": INVOICE_FROM_EMAIL},
        "to": [{"email": customer_email, "name": customer_name}],
        "subject": f"GenCirty Invoice #{invoice_number} - Payment Confirmed",
        "textContent": body,
        "attachment": [{
            "name": f"GenCirty_Invoice_{invoice_number}.pdf",
            "content": pdf_b64,
        }],
    }

    headers = {
        "api-key": os.environ.get("BREVO_API_KEY", ""),
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(BREVO_API_URL, json=payload, headers=headers)

    if response.status_code not in (200, 201):
        logger.error(f"Invoice email failed: {response.status_code} {response.text}")
    else:
        logger.info(f"Invoice sent to {customer_email} | Invoice #{invoice_number}")
