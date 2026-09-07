import logging
from datetime import date
from pathlib import Path
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.modules.schedules.models import (
    Project,
    ScheduleVersion,
    ScheduleActivity,
    ActivityDependency,
)
from app.modules.schedules.schemas import ProjectCreate
from app.modules.schedules.service import ScheduleService
from app.modules.field_capture.models import FieldReport, ProgressEvent
from app.modules.field_capture.schemas import RawTextReportCreate
from app.modules.field_capture.service import FieldCaptureService
from app.modules.semantic_matcher.models import ActivityMatchCandidate
from app.modules.semantic_matcher.service import SemanticMatcherService
from app.modules.dependency_validator.models import DependencyViolation
from app.modules.dependency_validator.service import DependencyValidatorService
from app.modules.review_inbox.models import ReviewAudit

logger = logging.getLogger("synapse.demo.service")

DEMO_PROJECT_CODE = "OIL-SYNAPSE-DEMO"
DEMO_PROJECT_NAME = "Oil India 30 KM Crude Oil Pipeline - Duliajan to Numaligarh"
DEMO_CLIENT_NAME = "Oil India Limited"

# 5 Core SIH Demo Scenario Definitions
DEMO_SCENARIOS = [
    {
        "scenario_id": "SCENARIO-1",
        "title": "High-Confidence Clean Match",
        "reporter_name": "Er. H. Barua (Survey Lead)",
        "report_date": date(2026, 10, 5),
        "raw_text": "Completed topographical survey and peg marking for 5 km along Ch 0+000 to Ch 5+000.",
        "expected_code": "ACT-1010",
        "description": "Standardized survey claim matches ACT-1010 with >0.85 confidence. Clean 1-click approval mutates actuals while preserving baseline.",
    },
    {
        "scenario_id": "SCENARIO-2",
        "title": "Ambiguous Match & Human Reassignment",
        "reporter_name": "Er. K. Saikia (Mainline Welding Engineer)",
        "report_date": date(2026, 11, 5),
        "raw_text": "Pipeline welding completed near the river crossing section.",
        "expected_code": "ACT-2030",
        "description": "Ambiguous scope between mainline welding (ACT-2030) and HDD river crossing (ACT-3010). Engineer reassigns candidate without premature schedule mutation.",
    },
    {
        "scenario_id": "SCENARIO-3",
        "title": "Dependency Blocker & Justified Override",
        "reporter_name": "Er. M. Phukan (Station Mechanical Lead)",
        "report_date": date(2026, 11, 12),
        "raw_text": "Valve Station 01 Manifold Piping & Actuator Mounting completed today at SV-01.",
        "expected_code": "ACT-5020",
        "description": "Predecessor ACT-5010 (Civil Raft) is unstarted. Hard violation blocks standard approval. Project Director provides justified override.",
    },
    {
        "scenario_id": "SCENARIO-4",
        "title": "Out-of-Scope / Unsafe Interpretation",
        "reporter_name": "Er. N. Gogoi (Site Admin)",
        "report_date": date(2026, 11, 1),
        "raw_text": "Security gate painting and boundary fence whitewashing completed at perimeter.",
        "expected_code": None,
        "description": "Out-of-scope maintenance work flagged as UNMATCHED (<0.50). Approval blocked; engineer rejection logged with zero schedule mutation.",
    },
    {
        "scenario_id": "SCENARIO-5",
        "title": "Multi-Event DPR Discretization",
        "reporter_name": "Er. D. Bora (Spread 1 Superintendent)",
        "report_date": date(2026, 10, 25),
        "raw_text": "Trenching completed for 450 m from Ch 20+000 to Ch 20+450.\nPipeline stringing completed for 25 joints in the same section.",
        "expected_code": "ACT-1030, ACT-2010",
        "description": "Multi-statement DPR parsed into 2 discrete ProgressEvents (Trenching & Stringing) matched and validated independently.",
    },
]


def _find_schedule_csv() -> Path:
    """Locates the oil_india_pipeline_sample.csv file reliably."""
    candidates = [
        Path("sample_data/schedules/oil_india_pipeline_sample.csv"),
        Path(__file__).resolve().parents[4] / "sample_data" / "schedules" / "oil_india_pipeline_sample.csv",
        Path(__file__).resolve().parents[3] / "sample_data" / "schedules" / "oil_india_pipeline_sample.csv",
        Path(__file__).resolve().parents[2] / "sample_data" / "schedules" / "oil_india_pipeline_sample.csv",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError("Could not locate sample_data/schedules/oil_india_pipeline_sample.csv")


class DemoService:
    """
    Manages repeatable seeding, resetting, and scenario verification for SIH 2026 evaluation.
    Guarantees that DEMO RESET -> SEED -> DEMO always produces the exact same starting state.
    """

    @staticmethod
    async def reset_demo(db: AsyncSession) -> Dict[str, Any]:
        """
        Idempotently wipes any existing demo project, associated schedules, DPRs,
        candidates, violations, and audit logs.
        """
        proj_res = await db.execute(select(Project).where(Project.code == DEMO_PROJECT_CODE))
        project = proj_res.scalars().first()

        if project:
            proj_id = project.id
            logger.info(f"Resetting existing demo project '{DEMO_PROJECT_CODE}' (ID: {proj_id})...")

            # 1. Delete audit logs associated with demo project
            await db.execute(delete(ReviewAudit).where(ReviewAudit.project_id == proj_id))

            # 2. Delete violations associated with demo project
            await db.execute(delete(DependencyViolation).where(DependencyViolation.project_id == proj_id))

            # 3. Delete match candidates for events in this project
            events_q = (
                select(ProgressEvent.id)
                .join(FieldReport, ProgressEvent.field_report_id == FieldReport.id)
                .where(FieldReport.project_id == proj_id)
            )
            event_ids = list((await db.execute(events_q)).scalars().all())
            if event_ids:
                await db.execute(
                    delete(ActivityMatchCandidate).where(
                        ActivityMatchCandidate.progress_event_id.in_(event_ids)
                    )
                )

            # 4. Delete progress events and field reports
            if event_ids:
                await db.execute(delete(ProgressEvent).where(ProgressEvent.id.in_(event_ids)))
            await db.execute(delete(FieldReport).where(FieldReport.project_id == proj_id))

            # 5. Delete schedule dependencies and activities
            versions_q = select(ScheduleVersion.id).where(ScheduleVersion.project_id == proj_id)
            version_ids = list((await db.execute(versions_q)).scalars().all())
            if version_ids:
                await db.execute(
                    delete(ActivityDependency).where(ActivityDependency.schedule_version_id.in_(version_ids))
                )
                await db.execute(
                    delete(ScheduleActivity).where(ScheduleActivity.schedule_version_id.in_(version_ids))
                )
                await db.execute(
                    delete(ScheduleVersion).where(ScheduleVersion.id.in_(version_ids))
                )

            # 6. Delete project
            await db.delete(project)
            await db.commit()
            logger.info(f"Demo project '{DEMO_PROJECT_CODE}' successfully purged.")

        return {
            "status": "RESET",
            "message": "Demo project and all associated data cleared. Ready for fresh seed.",
        }

    @staticmethod
    async def seed_demo(db: AsyncSession) -> Dict[str, Any]:
        """
        Deterministically creates the demo project, imports the 20-activity schedule,
        seeds the 5 core demo DPRs, runs hybrid semantic matching and deterministic validation,
        populating the Review Inbox and Execution Bridge.
        """
        # 1. Reset first to ensure 100% deterministic repeatability
        await DemoService.reset_demo(db)

        # 2. Create Demo Project
        project = await ScheduleService.create_project(
            db,
            ProjectCreate(
                name=DEMO_PROJECT_NAME,
                code=DEMO_PROJECT_CODE,
                client_name=DEMO_CLIENT_NAME,
                target_start_date=date(2026, 10, 1),
                target_finish_date=date(2027, 1, 5),
            ),
        )

        # 3. Read and Ingest Schedule CSV
        csv_path = _find_schedule_csv()
        csv_content = csv_path.read_text(encoding="utf-8")
        schedule_info = await ScheduleService.ingest_schedule_csv(
            db, project.id, csv_content, version_label="Oil India Baseline R0"
        )
        logger.info(f"Imported schedule with {schedule_info.get('activities_count', 20)} activities.")

        # 4. Seed the 5 Demo Scenarios
        seeded_scenarios: List[Dict[str, Any]] = []
        total_events = 0
        total_candidates = 0

        for sc in DEMO_SCENARIOS:
            # A. Ingest Field Report
            report = await FieldCaptureService.ingest_raw_text(
                db,
                RawTextReportCreate(
                    project_id=project.id,
                    raw_text=sc["raw_text"],
                    reporter_name=sc["reporter_name"],
                    report_date=sc["report_date"],
                ),
            )

            scenario_candidates = []
            for evt in report.events:
                total_events += 1
                # B. Run Hybrid Semantic Matching
                match_res = await SemanticMatcherService.run_matching_for_event(db, evt.id, top_k=3)
                for cand in match_res.candidates:
                    total_candidates += 1
                    # C. Run Phase 3 Deterministic Dependency Validation
                    val_res = await DependencyValidatorService.validate_candidate(db, cand.candidate_id)
                    scenario_candidates.append({
                        "candidate_id": cand.candidate_id,
                        "activity_code": cand.activity_code,
                        "confidence_score": cand.confidence_score,
                        "validation_decision": val_res.final_decision,
                        "violations_count": len(val_res.violations),
                    })

            seeded_scenarios.append({
                "scenario_id": sc["scenario_id"],
                "title": sc["title"],
                "report_id": report.id,
                "events_count": len(report.events),
                "candidates": scenario_candidates,
            })

        logger.info(
            f"Demo seeding complete for '{DEMO_PROJECT_CODE}': {len(seeded_scenarios)} scenarios, "
            f"{total_events} events, {total_candidates} candidates validated."
        )

        return {
            "status": "SEEDED",
            "project_id": project.id,
            "project_code": project.code,
            "project_name": project.name,
            "activities_count": schedule_info.get("activities_count", 20),
            "dependencies_count": schedule_info.get("dependencies_count", 25),
            "reports_count": len(seeded_scenarios),
            "events_count": total_events,
            "candidates_count": total_candidates,
            "scenarios": seeded_scenarios,
            "message": "Demo project successfully seeded with 5 verified scenarios ready for evaluation.",
        }

    @staticmethod
    async def get_demo_status(db: AsyncSession) -> Dict[str, Any]:
        """Checks if the demo project is currently active and returns summary stats."""
        proj_res = await db.execute(select(Project).where(Project.code == DEMO_PROJECT_CODE))
        project = proj_res.scalars().first()

        if not project:
            return {
                "is_seeded": False,
                "project_id": None,
                "message": "Demo project is not currently seeded.",
            }

        # Query counts
        acts_count = len(
            (
                await db.execute(
                    select(ScheduleActivity)
                    .join(ScheduleVersion, ScheduleActivity.schedule_version_id == ScheduleVersion.id)
                    .where(ScheduleVersion.project_id == project.id)
                )
            )
            .scalars()
            .all()
        )
        reports_count = len(
            (
                await db.execute(
                    select(FieldReport).where(FieldReport.project_id == project.id)
                )
            )
            .scalars()
            .all()
        )
        candidates_count = len(
            (
                await db.execute(
                    select(ActivityMatchCandidate)
                    .join(ProgressEvent, ActivityMatchCandidate.progress_event_id == ProgressEvent.id)
                    .join(FieldReport, ProgressEvent.field_report_id == FieldReport.id)
                    .where(FieldReport.project_id == project.id)
                )
            )
            .scalars()
            .all()
        )

        return {
            "is_seeded": True,
            "project_id": project.id,
            "project_code": project.code,
            "project_name": project.name,
            "activities_count": acts_count,
            "reports_count": reports_count,
            "candidates_count": candidates_count,
            "scenarios_available": [s["title"] for s in DEMO_SCENARIOS],
        }
