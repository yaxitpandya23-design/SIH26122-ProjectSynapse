from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.field_capture.schemas import (
    RawTextReportCreate,
    FieldReportResponse,
    ProgressEventResponse,
)
from app.modules.field_capture.service import FieldCaptureService

router = APIRouter(prefix="/field-reports", tags=["Field Reports & Progress Events"])


@router.post("/raw-text", response_model=FieldReportResponse, status_code=status.HTTP_201_CREATED)
async def submit_raw_text_report(
    report_in: RawTextReportCreate, db: AsyncSession = Depends(get_db)
):
    """Submit unstructured DPR site notes and extract structured progress events."""
    try:
        return await FieldCaptureService.ingest_raw_text(db, report_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process field report: {str(e)}",
        )


@router.get("", response_model=List[FieldReportResponse])
async def list_field_reports(
    project_id: Optional[str] = None, db: AsyncSession = Depends(get_db)
):
    """List submitted field progress reports."""
    return await FieldCaptureService.get_field_reports(db, project_id=project_id)


@router.get("/events/all", response_model=List[ProgressEventResponse])
async def list_progress_events(
    project_id: Optional[str] = None,
    discipline: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all extracted physical progress events."""
    return await FieldCaptureService.get_progress_events(
        db, project_id=project_id, discipline=discipline
    )
