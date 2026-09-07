import uuid
from datetime import datetime, date, timezone
from sqlalchemy import (
    Column,
    String,
    Float,
    Date,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base, VectorColumn


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now():
    return datetime.now(timezone.utc)


class FieldReport(Base):
    __tablename__ = "field_reports"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    report_date = Column(Date, default=date.today, nullable=False)
    reporter_name = Column(String(255), default="Site Execution Engineer", nullable=False)
    raw_source_text = Column(Text, nullable=False)
    source_type = Column(String(32), default="TEXT", nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="field_reports")
    events = relationship(
        "ProgressEvent", back_populates="field_report", cascade="all, delete-orphan"
    )


class ProgressEvent(Base):
    __tablename__ = "progress_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    field_report_id = Column(
        String(36), ForeignKey("field_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_description = Column(String(255), nullable=False)
    discipline = Column(String(64), default="GENERAL", nullable=False, index=True)
    location_chainage = Column(String(255), nullable=True)
    quantity_reported = Column(Float, nullable=True)
    uom = Column(String(32), nullable=True)
    status_claim = Column(String(64), default="IN_PROGRESS", nullable=False)
    event_date = Column(Date, nullable=True)
    raw_text_snippet = Column(Text, nullable=False)
    
    # 768-dim semantic embedding vector
    embedding = Column(VectorColumn(768), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    field_report = relationship("FieldReport", back_populates="events")
    match_candidates = relationship(
        "ActivityMatchCandidate", back_populates="progress_event", cascade="all, delete-orphan"
    )
    violations = relationship(
        "DependencyViolation", back_populates="progress_event", cascade="all, delete-orphan"
    )
