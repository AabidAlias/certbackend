"""
utils/helpers.py
Shared utility functions used across services.
"""
import uuid
import logging
from datetime import datetime
from pathlib import Path

# Configure module logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)


def generate_certificate_id() -> str:
    """Generate a unique certificate ID."""
    return str(uuid.uuid4())


def cm_to_px(cm: float, px_per_cm: float = 118.0) -> int:
    """Convert centimeters to pixels."""
    return int(cm * px_per_cm)


def safe_delete(path: str | Path) -> None:
    """Delete a file if it exists, silently."""
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass


def replace_template_vars(text: str, name: str) -> str:
    """Replace {{name}} placeholder in email templates."""
    return text.replace("{{name}}", name)


def utcnow() -> datetime:
    return datetime.utcnow()
