import uuid
from datetime import datetime, date, timezone
from typing import List, Optional
from sqlalchemy import (
    Column,
    String,
    Boolean,
    Integer,
    Float,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base, VectorColumn


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now():
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    code = Column(String(64), unique=True, nullable=False, index=True)
    client_name = Column(String(255), default="Oil India Limited", nullable=False)
    target_start_date = Column(Date, nullable=True)
    target_finish_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    schedule_versions = relationship(
        "ScheduleVersion", back_populates="project", cascade="all, delete-orphan"
    )
    field_reports = relationship(
        "FieldReport", back_populates="project", cascade="all, delete-orphan"
    )


class ScheduleVersion(Base):
    __tablename__ = "schedule_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    version_label = Column(String(64), default="Baseline Revision 0", nullable=False)
    is_active_baseline = Column(Boolean, default=True, nullable=False)
    imported_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="schedule_versions")
    activities = relationship(
        "ScheduleActivity", back_populates="schedule_version", cascade="all, delete-orphan"
    )
    dependencies = relationship(
        "ActivityDependency", back_populates="schedule_version", cascade="all, delete-orphan"
    )


class ScheduleActivity(Base):
    __tablename__ = "schedule_activities"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    schedule_version_id = Column(
        String(36), ForeignKey("schedule_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    activity_code = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    discipline = Column(String(64), default="GENERAL", nullable=False, index=True)
    wbs_code = Column(String(64), default="", nullable=False, index=True)
    wbs_name = Column(String(255), default="", nullable=True)
    planned_start = Column(Date, nullable=True)
    planned_finish = Column(Date, nullable=True)
    planned_duration_days = Column(Integer, default=0, nullable=False)
    actual_start = Column(Date, nullable=True)
    actual_finish = Column(Date, nullable=True)
    planned_quantity = Column(Float, default=0.0, nullable=False)
    actual_quantity = Column(Float, default=0.0, nullable=False)
    uom = Column(String(32), default="UNITS", nullable=True)
    physical_percent_complete = Column(Float, default=0.0, nullable=False)
    is_critical = Column(Boolean, default=False, nullable=False)
    total_float_days = Column(Integer, default=0, nullable=False)
    location_scope = Column(String(255), nullable=True)
    actuals_version = Column(Integer, default=1, nullable=False)
    
    # 768-dim semantic embedding vector
    embedding = Column(VectorColumn(768), nullable=True)

    # Relationships
    schedule_version = relationship("ScheduleVersion", back_populates="activities")
    predecessor_links = relationship(
        "ActivityDependency",
        foreign_keys="ActivityDependency.successor_id",
        back_populates="successor",
        cascade="all, delete-orphan",
    )
    successor_links = relationship(
        "ActivityDependency",
        foreign_keys="ActivityDependency.predecessor_id",
        back_populates="predecessor",
        cascade="all, delete-orphan",
    )
    match_candidates = relationship(
        "ActivityMatchCandidate", back_populates="activity", cascade="all, delete-orphan"
    )


class ActivityDependency(Base):
    __tablename__ = "activity_dependencies"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    schedule_version_id = Column(
        String(36), ForeignKey("schedule_versions.id", ondelete="CASCADE"), nullable=False
    )
    predecessor_id = Column(
        String(36), ForeignKey("schedule_activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    successor_id = Column(
        String(36), ForeignKey("schedule_activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dependency_type = Column(String(8), default="FS", nullable=False)  # FS, SS, FF, SF
    lag_days = Column(Integer, default=0, nullable=False)

    # Relationships
    schedule_version = relationship("ScheduleVersion", back_populates="dependencies")
    predecessor = relationship("ScheduleActivity", foreign_keys=[predecessor_id], back_populates="successor_links")
    successor = relationship("ScheduleActivity", foreign_keys=[successor_id], back_populates="predecessor_links")
