import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now():
    return datetime.now(timezone.utc)


class DependencyViolation(Base):
    __tablename__ = "dependency_violations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    progress_event_id = Column(
        String(36), ForeignKey("progress_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_candidate_id = Column(
        String(36), ForeignKey("match_candidates.id", ondelete="CASCADE"), nullable=True, index=True
    )
    activity_id = Column(
        String(36), ForeignKey("schedule_activities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    activity_code = Column(String(64), nullable=True)
    predecessor_activity_id = Column(
        String(36), ForeignKey("schedule_activities.id", ondelete="SET NULL"), nullable=True
    )
    predecessor_activity_code = Column(String(64), nullable=True)
    successor_activity_id = Column(
        String(36), ForeignKey("schedule_activities.id", ondelete="SET NULL"), nullable=True
    )
    successor_activity_code = Column(String(64), nullable=True)
    
    violation_type = Column(String(64), nullable=False)  # PREDECESSOR_INCOMPLETE, OUT_OF_SEQUENCE, QUANTITY_OVERRUN, DEPENDENCY_CYCLE, CRITICAL_PATH_RISK
    severity = Column(String(32), default="HARD_VIOLATION", nullable=False)  # HARD_VIOLATION, SOFT_WARNING
    description = Column(Text, nullable=False)
    expected_condition = Column(Text, nullable=True)
    observed_condition = Column(Text, nullable=True)
    detected_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    progress_event = relationship("ProgressEvent", back_populates="violations")
    activity = relationship("ScheduleActivity", foreign_keys=[activity_id])
    predecessor_activity = relationship("ScheduleActivity", foreign_keys=[predecessor_activity_id])
    successor_activity = relationship("ScheduleActivity", foreign_keys=[successor_activity_id])
