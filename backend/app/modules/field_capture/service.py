import logging
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_embedding_provider
from app.modules.schedules.models import Project
from app.modules.field_capture.models import FieldReport, ProgressEvent
from app.modules.field_capture.schemas import RawTextReportCreate
from app.modules.field_capture.extractor import FieldEventExtractor

logger = logging.getLogger("synapse.field_capture.service")


class FieldCaptureService:

    @staticmethod
    async def ingest_raw_text(
        db: AsyncSession, report_in: RawTextReportCreate
    ) -> FieldReport:
        # Validate project
        proj_res = await db.execute(select(Project).where(Project.id == report_in.project_id))
        project = proj_res.scalars().first()
        if not project:
            raise ValueError(f"Project with ID '{report_in.project_id}' not found.")

        # Create master FieldReport
        field_report = FieldReport(
            project_id=report_in.project_id,
            report_date=report_in.report_date,
            reporter_name=report_in.reporter_name,
            raw_source_text=report_in.raw_text,
            source_type="TEXT",
        )
        db.add(field_report)
        await db.flush()

        # Extract structured events via AI provider
        report_date_str = report_in.report_date.isoformat() if report_in.report_date else None
        extracted_events = await FieldEventExtractor.extract_events_from_text(
            report_in.raw_text, report_date=report_date_str
        )

        embedding_provider = get_embedding_provider()
        for evt in extracted_events:
            # Generate semantic embedding for the progress event
            semantic_text = f"{evt.work_description} | Discipline: {evt.discipline} | Loc: {evt.location_chainage or ''}"
            embedding = await embedding_provider.get_embedding(semantic_text)

            event_record = ProgressEvent(
                field_report_id=field_report.id,
                work_description=evt.work_description,
                discipline=evt.discipline,
                location_chainage=evt.location_chainage,
                quantity_reported=evt.quantity_reported,
                uom=evt.uom,
                status_claim=evt.status_claim,
                event_date=evt.event_date or report_in.report_date,
                raw_text_snippet=evt.raw_text_snippet,
                embedding=embedding,
            )
            db.add(event_record)

        await db.commit()
        await db.refresh(field_report)

        # Load events eagerly for response
        res = await db.execute(
            select(FieldReport)
            .where(FieldReport.id == field_report.id)
            .options(selectinload(FieldReport.events))
        )
        loaded_report = res.scalars().first()
        logger.info(
            f"Successfully saved FieldReport '{field_report.id}' with {len(extracted_events)} events."
        )
        return loaded_report or field_report

    @staticmethod
    async def get_field_reports(
        db: AsyncSession, project_id: Optional[str] = None
    ) -> List[FieldReport]:
        query = select(FieldReport).options(selectinload(FieldReport.events))
        if project_id:
            query = query.where(FieldReport.project_id == project_id)
        query = query.order_by(FieldReport.created_at.desc())
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_progress_events(
        db: AsyncSession,
        project_id: Optional[str] = None,
        discipline: Optional[str] = None,
    ) -> List[ProgressEvent]:
        query = select(ProgressEvent).join(FieldReport)
        if project_id:
            query = query.where(FieldReport.project_id == project_id)
        if discipline and discipline.upper() != "ALL":
            query = query.where(ProgressEvent.discipline == discipline.upper())
        query = query.order_by(ProgressEvent.created_at.desc())
        result = await db.execute(query)
        return list(result.scalars().all())
