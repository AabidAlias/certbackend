
```bash
cd backend

# Create and activate virtual environment
python -m venv venv
#source venv/bin/activate        # Linux/macOS
venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials (see below)
```

**Place your assets:**
```bash
# Put your font here:
cp /path/to/AlexBrush-Regular.ttf fonts/

# Put your certificate template here:
cp /path/to/certificate.png templates/certificate_template.png
```

**Start the backend:**
```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

API docs: http://localhost:8000/docs
