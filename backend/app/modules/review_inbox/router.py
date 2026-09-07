import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.review_inbox.schemas import (
    ReviewInboxItemDTO,
    ReviewCandidateDetailDTO,
    ReviewActionApproveDTO,
    ReviewActionOverrideDTO,
    ReviewActionRejectDTO,
    ReviewActionReassignDTO,
    ReviewActionEditDTO,
    ReviewMutationResponseDTO,
    ReviewAuditLogDTO,
    DashboardStatsDTO,
)
from app.modules.review_inbox.service import ScheduleUpdateService, ReviewInboxService

logger = logging.getLogger("synapse.review_inbox.router")

router = APIRouter(prefix="/review", tags=["Human-in-the-Loop Review & Approval"])


@router.get(
    "/inbox",
    response_model=List[ReviewInboxItemDTO],
    summary="List candidates in the review queue with validation badges",
)
async def get_inbox(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    status_filter: Optional[str] = Query(None, description="Filter by candidate status (AUTO_MATCHED, NEEDS_REVIEW, BLOCKED_BY_DEPENDENCY, APPLIED, REJECTED)"),
    severity_filter: Optional[str] = Query(None, description="Filter by violation severity (HARD_VIOLATION, SOFT_WARNING)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns candidate matches with multi-factor confidence, discrete validation indicators
    (predecessors, out-of-sequence, quantity, float), and eligibility flags for human approval.
    """
    try:
        return await ReviewInboxService.get_inbox_items(
            db=db,
            project_id=project_id,
            status_filter=status_filter,
            severity_filter=severity_filter,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error(f"Error fetching review inbox: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/candidates/{candidate_id}",
    response_model=ReviewCandidateDetailDTO,
    summary="Get 360-degree context for candidate inspection",
)
async def get_candidate_detail(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns complete 360-degree inspection detail for a single candidate:
    - Raw field note context & reporter details
    - Extracted ProgressEvent parameters
    - Target ScheduleActivity planned vs actual parameters
    - Confidence scoring breakdown
    - Deterministic dependency check results and blocker descriptions
    """
    try:
        return await ReviewInboxService.get_candidate_detail(db, candidate_id)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching candidate detail '{candidate_id}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/candidates/{candidate_id}/approve",
    response_model=ReviewMutationResponseDTO,
    summary="Approve candidate and apply progress to schedule actuals",
)
async def approve_candidate(
    candidate_id: str,
    payload: ReviewActionApproveDTO = ReviewActionApproveDTO(),
    db: AsyncSession = Depends(get_db),
):
    """
    Approves candidate and atomically updates ScheduleActivity actual fields.
    Guarantees:
    - Zero mutation of baseline planned parameters
    - Blocker guard: Cannot approve candidates with un-overridden hard violations
    - Idempotency: Re-submitting returns ALREADY_APPLIED without duplicate progress
    - Audit log persistence
    """
    try:
        return await ScheduleUpdateService.apply_approved_candidate(
            db=db,
            candidate_id=candidate_id,
            reviewer_user=payload.reviewer_user,
            remarks=payload.remarks,
            is_override=False,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Approval failed for '{candidate_id}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/candidates/{candidate_id}/override",
    response_model=ReviewMutationResponseDTO,
    summary="Override dependency blocker with mandatory reason and apply progress",
)
async def override_candidate(
    candidate_id: str,
    payload: ReviewActionOverrideDTO,
    db: AsyncSession = Depends(get_db),
):
    """
    Explicitly overrides hard dependency violations.
    Requires a detailed justification (min 5 characters) that is permanently recorded in the audit trail.
    """
    try:
        return await ScheduleUpdateService.apply_approved_candidate(
            db=db,
            candidate_id=candidate_id,
            reviewer_user=payload.reviewer_user,
            remarks=payload.remarks,
            is_override=True,
            override_reason=payload.override_reason,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Override failed for '{candidate_id}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/candidates/{candidate_id}/reject",
    response_model=ReviewMutationResponseDTO,
    summary="Reject candidate with explanation (zero schedule mutation)",
)
async def reject_candidate(
    candidate_id: str,
    payload: ReviewActionRejectDTO,
    db: AsyncSession = Depends(get_db),
):
    """
    Marks candidate as REJECTED.
    Zero mutation of schedule actuals or planned fields.
    Audit log recorded.
    """
    try:
        return await ReviewInboxService.reject_candidate(
            db=db,
            candidate_id=candidate_id,
            reason=payload.reason,
            reviewer_user=payload.reviewer_user,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Rejection failed for '{candidate_id}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/candidates/{candidate_id}/reassign",
    response_model=ReviewMutationResponseDTO,
    summary="Reassign candidate to different activity with fresh validation",
)
async def reassign_candidate(
    candidate_id: str,
    payload: ReviewActionReassignDTO,
    db: AsyncSession = Depends(get_db),
):
    """
    Reassigns progress candidate to another activity in the schedule.
    Guarantees:
    - Zero mutation of schedule actuals
    - Triggers immediate fresh deterministic validation against new target activity
    - Audit log recorded
    """
    try:
        return await ReviewInboxService.reassign_candidate(
            db=db,
            candidate_id=candidate_id,
            target_activity_id=payload.target_activity_id,
            reason=payload.reason,
            reviewer_user=payload.reviewer_user,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Reassignment failed for '{candidate_id}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/candidates/{candidate_id}/edit",
    response_model=ReviewMutationResponseDTO,
    summary="Edit reported event parameters and trigger fresh validation",
)
async def edit_candidate_event(
    candidate_id: str,
    payload: ReviewActionEditDTO,
    db: AsyncSession = Depends(get_db),
):
    """
    Edits reported progress parameters (quantity, UOM, status claim, date, description)
    without mutating baseline schedule.
    Invalidates previous validation and triggers fresh deterministic validation.
    """
    try:
        return await ReviewInboxService.edit_progress_event(
            db=db,
            candidate_id=candidate_id,
            payload=payload,
            reviewer_user=payload.reviewer_user,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Event edit failed for '{candidate_id}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/audit",
    response_model=List[ReviewAuditLogDTO],
    summary="List immutable review and mutation audit logs",
)
async def list_audit_logs(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    activity_id: Optional[str] = Query(None, description="Filter by activity ID"),
    action: Optional[str] = Query(None, description="Filter by action (APPROVED, OVERRIDDEN, REJECTED, REASSIGNED, EDITED)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns immutable audit trail for all human review decisions and schedule mutations.
    """
    try:
        return await ReviewInboxService.list_audit_logs(
            db=db,
            project_id=project_id,
            activity_id=activity_id,
            action=action,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error(f"Error listing audit logs: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/dashboard-stats",
    response_model=DashboardStatsDTO,
    summary="Get aggregated executive dashboard metrics",
)
async def get_dashboard_stats(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns high-level project KPIs:
    - Total reports & events captured
    - Candidate breakdown (Auto-matched, Needs Review, Blocked, Applied, Rejected)
    - Total schedule mutations
    - Unresolved dependency violations
    - Last schedule update details
    """
    try:
        return await ReviewInboxService.get_dashboard_stats(db=db, project_id=project_id)
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
