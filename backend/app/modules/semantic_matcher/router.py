from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.semantic_matcher.schemas import MatchRunResponse
from app.modules.semantic_matcher.service import SemanticMatcherService

router = APIRouter(prefix="/matching", tags=["Semantic Matching & Activity Linking"])


@router.post(
    "/progress-events/{event_id}",
    response_model=MatchRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate and return ranked schedule activity candidates",
)
async def match_progress_event(
    event_id: str,
    top_k: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """
    Executes hybrid retrieval, multi-factor confidence scoring, and arbitration
    for an individual ProgressEvent, saving ranked candidates to the database.
    """
    try:
        return await SemanticMatcherService.run_matching_for_event(db, event_id, top_k=top_k)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Semantic matching failed: {str(e)}",
        )


@router.get(
    "/progress-events/{event_id}/candidates",
    response_model=MatchRunResponse,
    summary="Retrieve previously generated candidates for a progress event",
)
async def get_event_candidates(
    event_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve persisted match candidates or run matching if none exist yet."""
    try:
        return await SemanticMatcherService.get_candidates_for_event(db, event_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch candidates: {str(e)}",
        )


@router.post(
    "/progress-events/{event_id}/run",
    response_model=MatchRunResponse,
    summary="Force re-run semantic matching for a progress event",
)
async def rerun_matching(
    event_id: str,
    top_k: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Re-executes the matching pipeline, updating match candidate records."""
    try:
        return await SemanticMatcherService.run_matching_for_event(db, event_id, top_k=top_k)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Semantic matching re-run failed: {str(e)}",
        )
