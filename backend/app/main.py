"""
app/main.py
FastAPI application factory.
"""
import logging
from contextlib import asynccontextmanager

import motor.motor_asyncio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)

client = None
db = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, db
    client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB_NAME]

    await db.certificates.create_index("batch_id")
    await db.certificates.create_index("certificate_id", unique=True)
    await db.certificates.create_index("cert_number")
    await db.certificates.create_index("status")
    await db.users.create_index("email", unique=True)
    await db.orders.create_index("order_id", unique=True)  # ✅ NEW: orders index

    logger.info(f"Connected to MongoDB: {settings.MONGO_DB_NAME}")
    yield
    client.close()


app = FastAPI(
    title="Smart Certificate Automation",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://gencirty.vercel.app",
        "https://gencirty-ll6ev0vzj-aabidalis-projects.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "Validation error on %s %s: %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


from app.api.certificate import router as cert_router
from app.api.auth import router as auth_router
from app.api.payments import router as payments_router  # ✅ NEW

app.include_router(cert_router)
app.include_router(auth_router)
app.include_router(payments_router)  # ✅ NEW


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


@app.head("/health")
async def health_head():
    return JSONResponse(content={})
