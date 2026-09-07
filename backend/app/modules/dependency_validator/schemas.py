from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DependencyViolationDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: Optional[str] = None
    progress_event_id: str
    match_candidate_id: Optional[str] = None
    activity_id: Optional[str] = None
    activity_code: Optional[str] = None
    predecessor_activity_id: Optional[str] = None
    predecessor_activity_code: Optional[str] = None
    successor_activity_id: Optional[str] = None
    successor_activity_code: Optional[str] = None
    violation_type: str  # PREDECESSOR_INCOMPLETE, OUT_OF_SEQUENCE, QUANTITY_OVERRUN, DEPENDENCY_CYCLE, CRITICAL_PATH_RISK
    severity: str  # HARD_VIOLATION, SOFT_WARNING
    description: str
    expected_condition: Optional[str] = None
    observed_condition: Optional[str] = None
    detected_at: datetime


class ValidationResultDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    candidate_id: str
    activity_id: str
    activity_code: str
    activity_name: str
    confidence_score: float
    semantic_decision: str
    final_decision: str  # AUTO_MATCHED, NEEDS_REVIEW, UNMATCHED, BLOCKED_BY_DEPENDENCY
    has_hard_violations: bool
    has_soft_warnings: bool
    violations: List[DependencyViolationDTO] = Field(default_factory=list)
    is_critical_path: bool = False
    total_float_days: int = 0
    summary_reason: str
    validated_at: datetime


class ValidationRequestDTO(BaseModel):
    candidate_id: Optional[str] = None
    progress_event_id: Optional[str] = None
    project_id: Optional[str] = None


class GraphNodeDTO(BaseModel):
    id: str
    activity_code: str
    name: str
    discipline: str
    duration_days: int
    early_start: Optional[str] = None
    early_finish: Optional[str] = None
    late_start: Optional[str] = None
    late_finish: Optional[str] = None
    total_float_days: int = 0
    is_critical: bool = False
    status: str = "NOT_STARTED"


class GraphEdgeDTO(BaseModel):
    predecessor_id: str
    successor_id: str
    predecessor_code: str
    successor_code: str
    dependency_type: str  # FS, SS, FF, SF
    lag_days: int = 0


class DependencyGraphDTO(BaseModel):
    project_id: str
    schedule_version_id: str
    nodes: List[GraphNodeDTO] = Field(default_factory=list)
    edges: List[GraphEdgeDTO] = Field(default_factory=list)
    has_cycles: bool = False
    cycles: List[List[str]] = Field(default_factory=list)
    topological_order: List[str] = Field(default_factory=list)
    critical_path_activities: List[str] = Field(default_factory=list)
    project_duration_days: int = 0
