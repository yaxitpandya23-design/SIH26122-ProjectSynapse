from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.schedules.schemas import (
    ProjectCreate,
    ProjectResponse,
    ScheduleActivityResponse,
    ScheduleUploadResponse,
)
from app.modules.schedules.service import ScheduleService

router = APIRouter(prefix="/schedules", tags=["Schedules & Projects"])


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(project_in: ProjectCreate, db: AsyncSession = Depends(get_db)):
    """Create a new infrastructure project."""
    return await ScheduleService.create_project(db, project_in)


@router.get("/projects", response_model=List[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    """List all infrastructure projects."""
    return await ScheduleService.get_projects(db)


@router.post("/upload-csv", response_model=ScheduleUploadResponse)
async def upload_schedule_csv(
    project_id: str = Form(...),
    version_label: str = Form("Baseline Revision 0"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload and parse a schedule CSV file into activities and dependencies."""
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only CSV files are supported.",
        )

    content_bytes = await file.read()
    csv_text = content_bytes.decode("utf-8", errors="replace")

    try:
        result = await ScheduleService.ingest_schedule_csv(
            db, project_id=project_id, csv_content=csv_text, version_label=version_label
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest schedule CSV: {str(e)}",
        )


@router.get("/{schedule_version_id}/activities", response_model=List[ScheduleActivityResponse])
async def get_schedule_activities(
    schedule_version_id: str,
    discipline: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List activities for a specific schedule version."""
    return await ScheduleService.get_activities_by_schedule(
        db, schedule_version_id=schedule_version_id, discipline=discipline
    )


@router.get("/project/{project_id}/activities", response_model=List[ScheduleActivityResponse])
async def get_project_activities(
    project_id: str,
    discipline: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List activities for the active baseline schedule of a project."""
    return await ScheduleService.get_activities_by_schedule(
        db, project_id=project_id, discipline=discipline
    )
