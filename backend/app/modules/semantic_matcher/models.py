import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    DateTime,
    ForeignKey,
    Text,
    JSON,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now():
    return datetime.now(timezone.utc)


class ActivityMatchCandidate(Base):
    __tablename__ = "match_candidates"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    progress_event_id = Column(
        String(36), ForeignKey("progress_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    activity_id = Column(
        String(36), ForeignKey("schedule_activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    confidence_score = Column(Float, default=0.0, nullable=False, index=True)
    score_breakdown = Column(JSON, default=dict, nullable=False)
    status = Column(String(32), default="PENDING_REVIEW", nullable=False, index=True)
    llm_reasoning = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    validated_activity_version = Column(Integer, default=1, nullable=True)

    # Relationships
    progress_event = relationship("ProgressEvent", back_populates="match_candidates")
    activity = relationship("ScheduleActivity", back_populates="match_candidates")
    review_audits = relationship(
        "ReviewAudit", back_populates="match_candidate", cascade="all, delete-orphan"
    )
    violations = relationship(
        "DependencyViolation",
        foreign_keys="DependencyViolation.match_candidate_id",
        cascade="all, delete-orphan",
    )
