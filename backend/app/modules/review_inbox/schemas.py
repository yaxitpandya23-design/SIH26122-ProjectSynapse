from datetime import datetime, date
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, ConfigDict, Field

from app.modules.dependency_validator.schemas import DependencyViolationDTO


class ReviewInboxItemDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    candidate_id: str
    progress_event_id: str
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    report_date: Optional[str] = None
    reporter_name: Optional[str] = None
    raw_text_snippet: str
    work_description: str
    discipline: str
    location_chainage: Optional[str] = None
    quantity_reported: Optional[float] = None
    uom: Optional[str] = None
    status_claim: str
    event_date: Optional[str] = None

    # Proposed Activity
    activity_id: str
    activity_code: str
    activity_name: str
    activity_discipline: str
    planned_quantity: float = 0.0
    actual_quantity: float = 0.0
    activity_uom: Optional[str] = None

    # AI Match Score & Status
    confidence_score: float
    score_breakdown: Dict[str, float] = Field(default_factory=dict)
    status: str  # AUTO_MATCHED, NEEDS_REVIEW, BLOCKED_BY_DEPENDENCY, UNMATCHED, APPLIED, REJECTED, STALE_REVIEW

    # Validation Checks
    has_hard_violations: bool = False
    has_soft_warnings: bool = False
    violations_count: int = 0
    is_critical: bool = False
    total_float_days: int = 0
    validation_checks: Dict[str, str] = Field(default_factory=dict)  # predecessor, sequence, quantity, critical_path
    blocker_reasons: List[str] = Field(default_factory=list)

    # Action flags
    can_approve: bool = False
    can_override: bool = False
    is_applied: bool = False


class ReviewCandidateDetailDTO(ReviewInboxItemDTO):
    raw_source_text: str = ""
    matching_reasons: List[str] = Field(default_factory=list)
    mismatch_reasons: List[str] = Field(default_factory=list)
    llm_reasoning: Optional[str] = None
    violations: List[DependencyViolationDTO] = Field(default_factory=list)
    previous_actuals: Dict[str, Any] = Field(default_factory=dict)
    is_stale: bool = False


class ReviewActionApproveDTO(BaseModel):
    reviewer_user: str = "Site Planning Engineer"
    remarks: Optional[str] = None


class ReviewActionOverrideDTO(BaseModel):
    override_reason: str = Field(
        ..., min_length=5, description="Mandatory rationale for overriding schedule violation"
    )
    reviewer_user: str = "Site Planning Engineer"
    remarks: Optional[str] = None


class ReviewActionRejectDTO(BaseModel):
    reason: str = Field(..., min_length=3, description="Reason for rejection")
    reviewer_user: str = "Site Planning Engineer"


class ReviewActionReassignDTO(BaseModel):
    target_activity_id: str
    reason: Optional[str] = None
    reviewer_user: str = "Site Planning Engineer"


class ReviewActionEditDTO(BaseModel):
    quantity_reported: Optional[float] = None
    uom: Optional[str] = None
    event_date: Optional[str] = None
    status_claim: Optional[str] = None
    work_description: Optional[str] = None
    reason: Optional[str] = None
    reviewer_user: str = "Site Planning Engineer"


class ReviewMutationResponseDTO(BaseModel):
    status: str  # APPLIED, ALREADY_APPLIED, REJECTED, REASSIGNED, EDITED, STALE_REVIEW
    message: str
    candidate_id: str
    activity_code: str
    action: str
    previous_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    audit_id: Optional[str] = None


class ReviewAuditLogDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: Optional[str] = None
    match_candidate_id: Optional[str] = None
    progress_event_id: Optional[str] = None
    activity_id: Optional[str] = None
    activity_code: Optional[str] = None
    activity_name: Optional[str] = None
    action: str
    decision: Optional[str] = None
    reviewer_user: str
    review_timestamp: datetime
    remarks: Optional[str] = None
    is_override: bool = False
    override_reason: Optional[str] = None
    previous_values: Dict[str, Any] = Field(default_factory=dict)
    new_values: Dict[str, Any] = Field(default_factory=dict)


class DashboardStatsDTO(BaseModel):
    total_reports: int = 0
    total_events: int = 0
    auto_matched: int = 0
    needs_review: int = 0
    blocked_by_dependency: int = 0
    applied: int = 0
    rejected: int = 0
    total_mutations: int = 0
    total_violations: int = 0
    unresolved_violations: int = 0  # backwards-compatible alias
    last_update: Optional[Dict[str, Any]] = None
