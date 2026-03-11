"""
services/pdf_generator.py
Generates certificate PDF — name position passed dynamically (not from .env).
"""
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from app.core.config import settings
from app.services.font_service import get_auto_sized_font
from app.utils.helpers import get_logger, cm_to_px

logger = get_logger(__name__)


def _load_plain_font(size: int = 28) -> ImageFont.FreeTypeFont:
    """Plain sans-serif font for certificate number — NOT AlexBrush."""
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def generate_certificate_pdf(
    name: str,
    certificate_id: str,
    cert_number: str,
    output_path: str | Path,
    name_x_cm: float = None,
    name_y_cm: float = None,
    text_box_width_cm: float = None,
    template_path: str | Path = None,
) -> Path:
    """
    Generate a PDF certificate.

    Args:
        name: Recipient name
        certificate_id: UUID
        cert_number: Human-readable code e.g. TEDxSNPSU-2026-A3F7K
        output_path: Where to save the PDF
        name_x_cm: X origin of text box in cm (overrides .env)
        name_y_cm: Y center of name in cm (overrides .env)
        text_box_width_cm: Width of text box in cm (overrides .env)
        template_path: Optional override for template PNG
    """
    template_path = Path(template_path or settings.TEMPLATE_PATH)
    output_path = Path(output_path)

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    # Use passed values or fall back to .env
    x_cm = name_x_cm if name_x_cm is not None else settings.NAME_X_CM
    y_cm = name_y_cm if name_y_cm is not None else settings.NAME_Y_CM
    w_cm = text_box_width_cm if text_box_width_cm is not None else settings.TEXT_BOX_WIDTH_CM

    # ── 1. Open background ────────────────────────────────────────────────────
    bg = Image.open(template_path).convert("RGBA")
    img_w, img_h = bg.size
    logger.info(f"Template: {img_w}x{img_h}px | Name: '{name}' | Pos: ({x_cm},{y_cm})cm")

    # ── 2. Transparent text layer ─────────────────────────────────────────────
    txt = Image.new("RGBA", bg.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(txt)

    # ── 3. Name position ──────────────────────────────────────────────────────
    origin_x = cm_to_px(x_cm, settings.CM_TO_PX)
    origin_y = cm_to_px(y_cm, settings.CM_TO_PX)
    box_w    = cm_to_px(w_cm, settings.CM_TO_PX)

    font, font_size = get_auto_sized_font(name)
    bbox = font.getbbox(name)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    text_x = origin_x + (box_w - tw) // 2
    text_y = origin_y - th // 2

    # ── 4. Draw name in black ─────────────────────────────────────────────────
    draw.text((text_x, text_y), name, font=font, fill=(0, 0, 0, 255))

    # ── 5. Draw cert number (bottom right, plain font) ────────────────────────
    cf = _load_plain_font(size=28)
    cb = cf.getbbox(cert_number)
    cw = cb[2] - cb[0]
    ch = cb[3] - cb[1]
    margin = cm_to_px(0.5, settings.CM_TO_PX)
    cx = img_w - cw - margin
    cy = img_h - ch - margin

    pad = 10
    draw.rounded_rectangle(
        [cx - pad, cy - pad, cx + cw + pad, cy + ch + pad],
        radius=6, fill=(255, 255, 255, 180)
    )
    draw.text((cx, cy), cert_number, font=cf, fill=(50, 50, 50, 255))

    # ── 6. Composite + convert ────────────────────────────────────────────────
    combined = Image.alpha_composite(bg, txt)
    rgb = combined.convert("RGB")

    # ── 7. Save as PDF ────────────────────────────────────────────────────────
    w_pt = img_w * 72 / settings.CERT_DPI
    h_pt = img_h * 72 / settings.CERT_DPI
    buf = io.BytesIO()
    rgb.save(buf, format="PNG", dpi=(settings.CERT_DPI, settings.CERT_DPI))
    buf.seek(0)

    c = canvas.Canvas(str(output_path), pagesize=(w_pt, h_pt))
    c.drawImage(ImageReader(buf), 0, 0, width=w_pt, height=h_pt)
    c.save()

    logger.info(f"PDF saved: {output_path}")
    return output_path
