import logging
from typing import List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_embedding_provider
from app.modules.schedules.models import (
    Project,
    ScheduleVersion,
    ScheduleActivity,
    ActivityDependency,
)
from app.modules.schedules.schemas import ProjectCreate
from app.modules.schedules.parsers.csv_parser import parse_schedule_csv, ParsedActivityItem

logger = logging.getLogger("synapse.schedules.service")


class ScheduleService:

    @staticmethod
    async def create_project(db: AsyncSession, project_in: ProjectCreate) -> Project:
        # Check if project code already exists
        result = await db.execute(select(Project).where(Project.code == project_in.code))
        existing = result.scalars().first()
        if existing:
            return existing

        project = Project(
            name=project_in.name,
            code=project_in.code,
            client_name=project_in.client_name,
            target_start_date=project_in.target_start_date,
            target_finish_date=project_in.target_finish_date,
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)
        return project

    @staticmethod
    async def get_projects(db: AsyncSession) -> List[Project]:
        result = await db.execute(select(Project).order_by(Project.created_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def get_project_by_id(db: AsyncSession, project_id: str) -> Optional[Project]:
        result = await db.execute(select(Project).where(Project.id == project_id))
        return result.scalars().first()

    @staticmethod
    async def ingest_schedule_csv(
        db: AsyncSession, project_id: str, csv_content: str, version_label: str = "Baseline Revision 0"
    ) -> dict:
        project = await ScheduleService.get_project_by_id(db, project_id)
        if not project:
            raise ValueError(f"Project with ID '{project_id}' not found.")

        # Deactivate previous baseline versions for this project
        await db.execute(
            update(ScheduleVersion)
            .where(ScheduleVersion.project_id == project_id)
            .values(is_active_baseline=False)
        )

        # Create new ScheduleVersion
        schedule_version = ScheduleVersion(
            project_id=project_id,
            version_label=version_label,
            is_active_baseline=True,
        )
        db.add(schedule_version)
        await db.flush()

        parsed_items = parse_schedule_csv(csv_content)
        if not parsed_items:
            raise ValueError("No valid activities found in uploaded CSV.")

        embedding_provider = get_embedding_provider()
        code_to_activity: dict[str, ScheduleActivity] = {}
        activities_to_insert: List[ScheduleActivity] = []

        for item in parsed_items:
            # Build semantic text representation for initial embedding
            semantic_text = f"{item.wbs_name or ''} {item.name} | Discipline: {item.discipline} | Scope: {item.location_scope or ''}"
            embedding = await embedding_provider.get_embedding(semantic_text)

            activity = ScheduleActivity(
                schedule_version_id=schedule_version.id,
                activity_code=item.activity_code,
                name=item.name,
                discipline=item.discipline,
                wbs_code=item.wbs_code,
                wbs_name=item.wbs_name,
                planned_start=item.planned_start,
                planned_finish=item.planned_finish,
                planned_duration_days=item.planned_duration_days,
                planned_quantity=item.planned_quantity,
                actual_quantity=0.0,
                uom=item.uom,
                physical_percent_complete=0.0,
                is_critical=item.is_critical,
                location_scope=item.location_scope,
                embedding=embedding,
            )
            activities_to_insert.append(activity)
            db.add(activity)

        await db.flush()

        for act in activities_to_insert:
            code_to_activity[act.activity_code] = act

        # Link dependencies
        dependencies_count = 0
        for item in parsed_items:
            successor_act = code_to_activity.get(item.activity_code)
            if not successor_act:
                continue

            for pred_str in item.predecessors_raw:
                # Format could be "ACT-1010" or "ACT-1010:FS:0"
                parts = pred_str.split(":")
                pred_code = parts[0].strip()
                dep_type = parts[1].strip().upper() if len(parts) > 1 else "FS"
                lag = int(parts[2].strip()) if len(parts) > 2 and parts[2].strip().isdigit() else 0

                pred_act = code_to_activity.get(pred_code)
                if pred_act and pred_act.id != successor_act.id:
                    dep = ActivityDependency(
                        schedule_version_id=schedule_version.id,
                        predecessor_id=pred_act.id,
                        successor_id=successor_act.id,
                        dependency_type=dep_type,
                        lag_days=lag,
                    )
                    db.add(dep)
                    dependencies_count += 1

        await db.commit()
        logger.info(
            f"Imported {len(activities_to_insert)} activities and {dependencies_count} dependencies "
            f"for project {project_id} (Version: {schedule_version.id})."
        )

        return {
            "project_id": project_id,
            "schedule_version_id": schedule_version.id,
            "activities_imported": len(activities_to_insert),
            "dependencies_imported": dependencies_count,
            "message": f"Successfully ingested {len(activities_to_insert)} activities from schedule CSV.",
        }

    @staticmethod
    async def get_activities_by_schedule(
        db: AsyncSession,
        schedule_version_id: Optional[str] = None,
        project_id: Optional[str] = None,
        discipline: Optional[str] = None,
    ) -> List[ScheduleActivity]:
        query = select(ScheduleActivity)
        if schedule_version_id:
            query = query.where(ScheduleActivity.schedule_version_id == schedule_version_id)
        elif project_id:
            # Get active baseline version for project
            v_query = select(ScheduleVersion.id).where(
                ScheduleVersion.project_id == project_id,
                ScheduleVersion.is_active_baseline == True
            ).order_by(ScheduleVersion.imported_at.desc())
            v_result = await db.execute(v_query)
            active_version_id = v_result.scalars().first()
            if active_version_id:
                query = query.where(ScheduleActivity.schedule_version_id == active_version_id)
            else:
                return []

        if discipline and discipline.upper() != "ALL":
            query = query.where(ScheduleActivity.discipline == discipline.upper())

        query = query.order_by(ScheduleActivity.wbs_code, ScheduleActivity.activity_code)
        result = await db.execute(query)
        return list(result.scalars().all())
