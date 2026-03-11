"""
core/config.py
Centralized configuration using environment variables.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings:
    # App
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", 8000))
    FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

    # MongoDB
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "smart_certificates")

    # Gmail
    GMAIL_ADDRESS: str = os.getenv("GMAIL_ADDRESS", "")
    GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "")

    # Paths
    FONTS_DIR: Path = BASE_DIR / "fonts"
    TEMPLATES_DIR: Path = BASE_DIR / "templates"
    GENERATED_DIR: Path = BASE_DIR / "generated"
    FONT_PATH: Path = FONTS_DIR / "AlexBrush-Regular.ttf"
    TEMPLATE_PATH: Path = TEMPLATES_DIR / "certificate_template.png"

    # Certificate
    CERT_DPI: int = int(os.getenv("CERT_DPI", 300))
    CM_TO_PX: float = 118.0  # 1cm ≈ 118px at 300 DPI
    NAME_X_CM: float = float(os.getenv("NAME_X_CM", 8.62))
    NAME_Y_CM: float = float(os.getenv("NAME_Y_CM", 9.21))
    TEXT_BOX_WIDTH_CM: float = float(os.getenv("TEXT_BOX_WIDTH_CM", 18.81))
    DEFAULT_FONT_SIZE: int = int(os.getenv("DEFAULT_FONT_SIZE", 72))
    MIN_FONT_SIZE: int = int(os.getenv("MIN_FONT_SIZE", 36))

    # Email
    EMAIL_DELAY_SECONDS: float = 1.0

settings = Settings()

# Ensure directories exist
settings.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
