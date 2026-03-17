from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class DocumentAnalysis(Base):
    __tablename__ = "document_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_name: Mapped[str] = mapped_column(String(255), index=True)
    document_hash: Mapped[str] = mapped_column(String(64), index=True, unique=True)
    document_type: Mapped[str] = mapped_column(String(64), default="indefinido")
    raw_text: Mapped[str] = mapped_column(Text)
    structured_json: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[str] = mapped_column(Text)
    risks_json: Mapped[dict] = mapped_column(JSON)
    simplified_explanation: Mapped[str] = mapped_column(Text)
    s3_key: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
