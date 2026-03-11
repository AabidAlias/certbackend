# Backend — Smart Certificate Automation

FastAPI backend for generating and emailing personalized certificates.

## Quick Start

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit with your values
uvicorn app.main:app --reload
```

## Key Files

| File | Purpose |
|------|---------|
| `app/main.py` | App factory, startup hooks, CORS, global error handler |
| `app/core/config.py` | All settings loaded from `.env` |
| `app/api/certificate.py` | REST endpoints |
| `app/services/pdf_generator.py` | Certificate image compositing + PDF export |
| `app/services/email_service.py` | Async Gmail SMTP sending |
| `app/services/csv_service.py` | CSV parsing + validation |
| `app/services/font_service.py` | TTF loading + auto font-size fitting |
| `app/models/certificate_model.py` | Pydantic request/response models |
| `app/utils/helpers.py` | Shared utilities (UUID, cm→px, logging) |

## Certificate Positioning

Coordinates are set in `.env` as `NAME_X_CM` and `NAME_Y_CM`.
Conversion: `1 cm × 118 = pixels` (at 300 DPI).

The name is **horizontally centered** within a box of width `TEXT_BOX_WIDTH_CM`.
