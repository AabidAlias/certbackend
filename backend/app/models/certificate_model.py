"""
models/certificate_model.py
MongoDB document schema and Pydantic models for certificates.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr
from enum import Enum


class CertificateStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class CertificateCreate(BaseModel):
    """Input model for creating a certificate record."""
    name: str
    email: EmailStr


class CertificateDocument(BaseModel):
    """Full MongoDB document model."""
    certificate_id: str
    name: str
    email: str
    status: CertificateStatus = CertificateStatus.PENDING
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = None

    class Config:
        use_enum_values = True

    def to_dict(self) -> dict:
        return {
            "certificate_id": self.certificate_id,
            "name": self.name,
            "email": self.email,
            "status": self.status,
            "file_path": self.file_path,
            "error_message": self.error_message,
            "created_at": self.created_at or datetime.utcnow(),
        }


class BatchRequest(BaseModel):
    """Request model for starting a batch send."""
    email_subject: str
    email_body: str
