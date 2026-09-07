from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class ScoreBreakdown(BaseModel):
    """Normalized [0, 1] component score breakdown."""
    semantic: float = Field(..., ge=0.0, le=1.0, description="Semantic / textual similarity (40%)")
    discipline: float = Field(..., ge=0.0, le=1.0, description="Trade / discipline compatibility (20%)")
    location: float = Field(..., ge=0.0, le=1.0, description="Chainage / spatial alignment (20%)")
    quantity: float = Field(..., ge=0.0, le=1.0, description="UOM and quantity bounds compatibility (10%)")
    temporal: float = Field(..., ge=0.0, le=1.0, description="Schedule window plausibility (10%)")
    final: float = Field(..., ge=0.0, le=1.0, description="Final weighted composite confidence score")


class MatchCandidateItem(BaseModel):
    """Detailed explainable candidate activity returned to client."""
    candidate_id: Optional[str] = None
    activity_id: str
    activity_code: str
    activity_name: str
    discipline: str
    wbs_code: str
    wbs_name: Optional[str] = None
    location_scope: Optional[str] = None
    planned_quantity: float
    actual_quantity: float = 0.0
    uom: Optional[str] = None
    confidence_score: float
    score_breakdown: ScoreBreakdown
    ranking: int
    matching_reasons: List[str] = []
    mismatch_reasons: List[str] = []
    decision_status: str  # AUTO_MATCHED, NEEDS_REVIEW, UNMATCHED, BLOCKED_BY_DEPENDENCY
    llm_reasoning: Optional[str] = None
    validation_status: Optional[str] = None
    validation_summary: Optional[str] = None
    has_dependency_violations: bool = False


class MatchRunResponse(BaseModel):
    """Response payload for a semantic matching execution run."""
    event_id: str
    event_work_description: str
    event_discipline: str
    event_location: Optional[str] = None
    event_quantity: Optional[float] = None
    event_uom: Optional[str] = None
    top_decision: str
    arbitration_applied: bool = False
    arbitration_reasoning: Optional[str] = None
    candidates: List[MatchCandidateItem] = []
