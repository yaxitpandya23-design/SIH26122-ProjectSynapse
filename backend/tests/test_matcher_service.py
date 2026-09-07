import pytest
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.schedules.models import Project, ScheduleVersion, ScheduleActivity
from app.modules.field_capture.models import FieldReport, ProgressEvent
from app.modules.semantic_matcher.service import SemanticMatcherService
from app.modules.semantic_matcher.arbitration import arbitrate_close_candidates
from app.modules.semantic_matcher.schemas import MatchCandidateItem, ScoreBreakdown
from app.ai.mock_provider import MockProvider


@pytest.mark.asyncio
async def test_close_candidate_arbitration_trigger():
    # Setup two candidates with very close confidence scores (e.g. 0.78 and 0.75, diff = 0.03 < 0.15)
    cand1 = MatchCandidateItem(
        activity_id="act-welding",
        activity_code="ACT-2030",
        activity_name="Mainline Pipe Joint Shielded Metal Arc Welding",
        discipline="PIPING",
        wbs_code="1.2.2",
        planned_quantity=2400.0,
        confidence_score=0.78,
        score_breakdown=ScoreBreakdown(
            semantic=0.8, discipline=1.0, location=0.75, quantity=0.7, temporal=0.75, final=0.78
        ),
        ranking=1,
        decision_status="NEEDS_REVIEW",
    )
    cand2 = MatchCandidateItem(
        activity_id="act-tiein",
        activity_code="ACT-2070",
        activity_name="Mainline Tie-in Welding & Golden Joints",
        discipline="PIPING",
        wbs_code="1.2.4",
        planned_quantity=25.0,
        confidence_score=0.75,
        score_breakdown=ScoreBreakdown(
            semantic=0.76, discipline=1.0, location=0.75, quantity=0.6, temporal=0.75, final=0.75
        ),
        ranking=2,
        decision_status="NEEDS_REVIEW",
    )

    event = ProgressEvent(
        id="evt-ambiguous",
        field_report_id="rep-1",
        work_description="Pipeline welding completed near the crossing",
        discipline="PIPING",
        raw_text_snippet="Pipeline welding completed near the crossing",
    )

    applied, reason = await arbitrate_close_candidates(event, [cand1, cand2], threshold_margin=0.15)
    assert applied is True
    assert reason is not None
    assert cand1.llm_reasoning is not None
    assert "[AI Arbitration]" in cand1.llm_reasoning


@pytest.mark.asyncio
async def test_matcher_service_does_not_modify_schedule_data(client, prepare_database):
    from tests.conftest import TestingSessionLocal

    provider = MockProvider()
    async with TestingSessionLocal() as db:
        # Create Project & Baseline Schedule
        proj = Project(name="Test Project", code="TP-001", client_name="Oil India Limited")
        db.add(proj)
        await db.flush()

        sv = ScheduleVersion(project_id=proj.id, version_label="Rev 0", is_active_baseline=True)
        db.add(sv)
        await db.flush()

        # Add Activity with known initial actual_quantity = 0.0
        act_emb = await provider.get_embedding("Trench Excavation for 16-inch Pipeline")
        act = ScheduleActivity(
            schedule_version_id=sv.id,
            activity_code="ACT-1030",
            name="Trench Excavation for 16-inch Pipeline",
            discipline="CIVIL",
            wbs_code="1.2.1",
            planned_quantity=30000.0,
            actual_quantity=0.0,
            physical_percent_complete=0.0,
            uom="M",
            embedding=act_emb,
        )
        db.add(act)
        await db.flush()

        # Add Field Report & Progress Event
        rep = FieldReport(project_id=proj.id, reporter_name="Site Eng", raw_source_text="DPR text")
        db.add(rep)
        await db.flush()

        evt_emb = await provider.get_embedding("Excavator dug 620m pipeline trench")
        event = ProgressEvent(
            field_report_id=rep.id,
            work_description="Trench excavation and grading",
            discipline="CIVIL",
            location_chainage="Ch 08+400 to Ch 09+020",
            quantity_reported=620.0,
            uom="M",
            raw_text_snippet="Excavator dug 620m pipeline trench",
            embedding=evt_emb,
        )
        db.add(event)
        await db.commit()
        await db.refresh(act)
        await db.refresh(event)

        initial_actual_qty = act.actual_quantity
        initial_pct = act.physical_percent_complete

        # Execute matching
        result = await SemanticMatcherService.run_matching_for_event(db, event.id, top_k=5)
        assert len(result.candidates) > 0

        # Verify ScheduleActivity was NOT mutated
        await db.refresh(act)
        assert act.actual_quantity == initial_actual_qty
        assert act.physical_percent_complete == initial_pct
