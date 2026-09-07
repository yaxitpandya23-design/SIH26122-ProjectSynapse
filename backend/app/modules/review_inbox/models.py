import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Boolean,
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


class ReviewAudit(Base):
    __tablename__ = "review_audits"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    match_candidate_id = Column(
        String(36), ForeignKey("match_candidates.id", ondelete="CASCADE"), nullable=True, index=True
    )
    progress_event_id = Column(
        String(36), ForeignKey("progress_events.id", ondelete="CASCADE"), nullable=True, index=True
    )
    activity_id = Column(
        String(36), ForeignKey("schedule_activities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    activity_code = Column(String(64), nullable=True, index=True)
    action = Column(String(32), default="APPROVED", nullable=False, index=True)  # APPROVED, REJECTED, REASSIGNED, EDITED, OVERRIDDEN, APPLIED
    decision = Column(String(32), default="APPROVE", nullable=False)  # APPROVE, OVERRIDE, REJECT, REASSIGN, EDIT
    reviewer_user = Column(String(128), default="Site Planning Engineer", nullable=False)
    review_timestamp = Column(DateTime, default=utc_now, nullable=False, index=True)
    remarks = Column(Text, nullable=True)
    is_override = Column(Boolean, default=False, nullable=False)
    override_reason = Column(Text, nullable=True)
    previous_values = Column(JSON, default=dict, nullable=False)
    new_values = Column(JSON, default=dict, nullable=False)

    # Relationships
    match_candidate = relationship("ActivityMatchCandidate", back_populates="review_audits")
    activity = relationship("ScheduleActivity")
    project = relationship("Project")
    progress_event = relationship("ProgressEvent")

