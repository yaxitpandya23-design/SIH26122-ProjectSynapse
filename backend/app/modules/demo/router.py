import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.demo.service import DemoService

logger = logging.getLogger("synapse.demo.router")

router = APIRouter(prefix="/demo", tags=["SIH Demo Engine"])


@router.post(
    "/seed",
    summary="Seed Repeatable SIH 2026 Demo Dataset",
    description=(
        "Deterministically initializes the Oil India 30 KM Pipeline construction project, "
        "imports 20 realistic schedule activities and 25 dependencies, and seeds the 5 core demo "
        "scenarios through the complete extraction, matching, and validation pipeline."
    ),
    status_code=status.HTTP_201_CREATED,
)
async def seed_demo_dataset(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    try:
        result = await DemoService.seed_demo(db)
        return result
    except Exception as e:
        logger.error(f"Demo seeding failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to seed demo dataset: {str(e)}",
        )


@router.post(
    "/reset",
    summary="Reset Demo Project to Pristine Baseline",
    description=(
        "Idempotently clears all demo progress, candidates, actuals, and audit records, "
        "restoring the exact initial demo baseline state."
    ),
    status_code=status.HTTP_200_OK,
)
async def reset_demo_dataset(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    try:
        result = await DemoService.reset_demo(db)
        return result
    except Exception as e:
        logger.error(f"Demo reset failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset demo dataset: {str(e)}",
        )


@router.get(
    "/status",
    summary="Check Demo Project Seeding Status",
    description="Returns whether the demo project is active and summary statistics.",
    status_code=status.HTTP_200_OK,
)
async def get_demo_status(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    try:
        return await DemoService.get_demo_status(db)
    except Exception as e:
        logger.error(f"Error checking demo status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve demo status: {str(e)}",
        )
