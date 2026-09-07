import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.modules.dependency_validator.schemas import (
    ValidationResultDTO,
    ValidationRequestDTO,
    DependencyViolationDTO,
    DependencyGraphDTO,
)
from app.modules.dependency_validator.service import DependencyValidatorService
from app.modules.semantic_matcher.models import ActivityMatchCandidate

logger = logging.getLogger("synapse.dependency_validator.router")

router = APIRouter(prefix="/validation", tags=["Schedule Dependency Validation"])


@router.post(
    "/candidates/{candidate_id}",
    response_model=ValidationResultDTO,
    summary="Validate a candidate against schedule dependencies, sequence, and quantity constraints",
)
async def validate_candidate(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Executes deterministic dependency validation for a specific match candidate.
    Checks FS/SS/FF/SF dependencies, lag sequencing, quantity overruns, and critical path float.
    Persists violations and returns explainable decision.
    """
    try:
        result = await DependencyValidatorService.validate_candidate(db, candidate_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Validation error for candidate '{candidate_id}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Validation failed: {str(e)}")


@router.get(
    "/candidates/{candidate_id}",
    response_model=ValidationResultDTO,
    summary="Retrieve validation result for a candidate",
)
async def get_candidate_validation(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves or calculates the validation evaluation for a specific candidate.
    """
    try:
        return await DependencyValidatorService.validate_candidate(db, candidate_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/run",
    response_model=List[ValidationResultDTO],
    summary="Run validation for a progress event's candidate pool",
)
async def run_validation(
    payload: ValidationRequestDTO,
    db: AsyncSession = Depends(get_db),
):
    """
    Runs deterministic dependency validation across candidates.
    Can validate by candidate_id or by progress_event_id.
    """
    if payload.candidate_id:
        try:
            res = await DependencyValidatorService.validate_candidate(db, payload.candidate_id)
            return [res]
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    if payload.progress_event_id:
        try:
            return await DependencyValidatorService.validate_progress_event(db, payload.progress_event_id)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Must provide either 'candidate_id' or 'progress_event_id'."
    )


@router.get(
    "/violations",
    response_model=List[DependencyViolationDTO],
    summary="List detected dependency violations with filtering",
)
async def list_violations(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    progress_event_id: Optional[str] = Query(None, description="Filter by progress event ID"),
    activity_id: Optional[str] = Query(None, description="Filter by activity ID"),
    severity: Optional[str] = Query(None, description="Filter by severity (HARD_VIOLATION, SOFT_WARNING)"),
    violation_type: Optional[str] = Query(None, description="Filter by violation type"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves logged dependency violations with multi-field filtering for audit trail.
    """
    return await DependencyValidatorService.list_violations(
        db,
        project_id=project_id,
        progress_event_id=progress_event_id,
        activity_id=activity_id,
        severity=severity,
        violation_type=violation_type,
        limit=limit,
    )


@router.get(
    "/projects/{project_id}/graph",
    response_model=DependencyGraphDTO,
    summary="Get project dependency graph topology and Critical Path metrics",
)
async def get_project_graph(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the full DAG topology, edge relationships, CPM early/late schedules,
    total floats, and critical path activities for a project.
    """
    try:
        return await DependencyValidatorService.get_project_graph(db, project_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to compute graph for project '{project_id}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
