"""
services/font_service.py
Handles font loading and auto-resizing for certificate names.
"""
from PIL import ImageFont
from pathlib import Path

from app.core.config import settings
from app.utils.helpers import get_logger, cm_to_px

logger = get_logger(__name__)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    """Load the AlexBrush font at the given size."""
    font_path = str(settings.FONT_PATH)
    if not Path(font_path).exists():
        raise FileNotFoundError(f"Font not found: {font_path}")
    return ImageFont.truetype(font_path, size)


def get_auto_sized_font(name: str) -> tuple[ImageFont.FreeTypeFont, int]:
    """
    Returns a (font, font_size) tuple where the font is auto-sized
    so that the rendered name fits within the configured text box width.
    
    Starts at DEFAULT_FONT_SIZE and decreases to MIN_FONT_SIZE.
    """
    max_width_px = cm_to_px(settings.TEXT_BOX_WIDTH_CM, settings.CM_TO_PX)
    font_size = settings.DEFAULT_FONT_SIZE

    while font_size >= settings.MIN_FONT_SIZE:
        font = load_font(font_size)
        bbox = font.getbbox(name)
        text_width = bbox[2] - bbox[0]
        if text_width <= max_width_px:
            logger.debug(f"Font size {font_size} fits for name '{name}' (width={text_width}px)")
            return font, font_size
        font_size -= 2  # decrease by 2pt steps

    # Fallback: use minimum size regardless
    logger.warning(f"Name '{name}' too long; using minimum font size {settings.MIN_FONT_SIZE}")
    return load_font(settings.MIN_FONT_SIZE), settings.MIN_FONT_SIZE
