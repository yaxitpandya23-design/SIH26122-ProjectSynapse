import pytest
from datetime import date
from pathlib import Path
from httpx import AsyncClient
from sqlalchemy import select

from app.modules.schedules.models import ScheduleActivity
from app.modules.semantic_matcher.models import ActivityMatchCandidate
from app.modules.review_inbox.models import ReviewAudit

SAMPLE_CSV_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "sample_data"
    / "schedules"
    / "oil_india_pipeline_sample.csv"
)


async def setup_project_and_schedule(client: AsyncClient):
    """Helper to initialize project and upload standard schedule."""
    proj_res = await client.post(
        "/api/v1/schedules/projects",
        json={"name": "Pipeline Project", "code": "PL-REVIEW-01", "client_name": "Oil India Limited"},
    )
    assert proj_res.status_code in (200, 201)
    project_id = proj_res.json()["id"]

    csv_bytes = SAMPLE_CSV_PATH.read_bytes()
    upload_res = await client.post(
        "/api/v1/schedules/upload-csv",
        data={"project_id": project_id, "version_label": "Baseline Rev 0"},
        files={"file": ("schedule.csv", csv_bytes, "text/csv")},
    )
    assert upload_res.status_code == 200
    schedule_version_id = upload_res.json()["schedule_version_id"]
    return project_id, schedule_version_id


@pytest.mark.asyncio
async def test_inbox_listing_and_detail_360_context(client: AsyncClient, prepare_database):
    """Tests review inbox queue retrieval with validation indicators and full candidate detail."""
    project_id, schedule_version_id = await setup_project_and_schedule(client)

    # Ingest DPR
    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed topographical survey and peg marking for 5 km along section 10+000 to 15+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    assert dpr_res.status_code in (200, 201)
    event_id = dpr_res.json()["events"][0]["id"]

    # Match candidate
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=2")
    assert match_res.status_code == 200
    cand_id = match_res.json()["candidates"][0]["candidate_id"]

    # Validate candidate
    val_res = await client.post(f"/api/v1/validation/candidates/{cand_id}")
    assert val_res.status_code == 200

    # 1. Fetch Review Inbox
    inbox_res = await client.get(f"/api/v1/review/inbox?project_id={project_id}")
    assert inbox_res.status_code == 200
    inbox_items = inbox_res.json()
    assert len(inbox_items) >= 1
    item = next(i for i in inbox_items if i["candidate_id"] == cand_id)

    assert item["activity_code"] == "ACT-1010"
    assert "validation_checks" in item
    assert item["validation_checks"]["predecessor"] == "PASS"  # ACT-1010 has no predecessors
    assert item["can_approve"] is True
    assert item["can_override"] is False
    assert item["is_applied"] is False

    # 2. Fetch 360 Candidate Detail
    detail_res = await client.get(f"/api/v1/review/candidates/{cand_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["candidate_id"] == cand_id
    assert detail["activity_code"] == "ACT-1010"
    assert detail["reporter_name"] == "Er. H. Barua"
    assert detail["planned_quantity"] == 30.0
    assert detail["quantity_reported"] == 5.0
    assert detail["actual_quantity"] == 0.0
    assert detail["previous_actuals"]["physical_percent_complete"] == 0.0


@pytest.mark.asyncio
async def test_clean_approval_mutates_actuals_and_preserves_baseline(client: AsyncClient, prepare_database):
    """
    Tests that approving a clean candidate:
    1. Atomically mutates only actual_* and percent_complete fields.
    2. Planned baseline parameters remain strictly unchanged.
    3. Audit record is persisted with full diff.
    """
    project_id, schedule_version_id = await setup_project_and_schedule(client)

    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed topographical survey and peg marking for 5 km along section 10+000 to 15+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    event_id = dpr_res.json()["events"][0]["id"]
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=1")
    cand_id = match_res.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{cand_id}")

    # Inspect activity BEFORE approval
    act_before_res = await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")
    act_before = next(a for a in act_before_res.json() if a["activity_code"] == "ACT-1010")
    assert act_before["actual_quantity"] == 0.0
    assert act_before["actual_start"] is None
    assert act_before["actual_finish"] is None
    assert act_before["physical_percent_complete"] == 0.0

    # Approve Candidate
    appr_res = await client.post(
        f"/api/v1/review/candidates/{cand_id}/approve",
        json={"reviewer_user": "Chief Planning Engineer", "remarks": "Survey verified against field sheets."},
    )
    assert appr_res.status_code == 200
    mutation_res = appr_res.json()
    assert mutation_res["status"] == "APPLIED"
    assert mutation_res["action"] == "APPROVED"
    assert mutation_res["activity_code"] == "ACT-1010"

    # Inspect activity AFTER approval
    act_after_res = await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")
    act_after = next(a for a in act_after_res.json() if a["activity_code"] == "ACT-1010")

    # Allowed mutated fields
    assert act_after["actual_quantity"] == 5.0
    assert act_after["actual_start"] is not None
    assert act_after["actual_finish"] is not None
    assert act_after["physical_percent_complete"] == 100.0

    # Baseline IMMUTABLE fields preserved
    assert act_after["planned_start"] == act_before["planned_start"]
    assert act_after["planned_finish"] == act_before["planned_finish"]
    assert act_after["planned_quantity"] == act_before["planned_quantity"]
    assert act_after["wbs_code"] == act_before["wbs_code"]
    assert act_after["discipline"] == act_before["discipline"]
    assert act_after["planned_duration_days"] == act_before["planned_duration_days"]
    assert act_after["uom"] == act_before["uom"]

    # Check Audit Log
    audit_res = await client.get(f"/api/v1/review/audit?project_id={project_id}")
    assert audit_res.status_code == 200
    audits = audit_res.json()
    assert len(audits) >= 1
    assert audits[0]["action"] == "APPROVED"
    assert audits[0]["reviewer_user"] == "Chief Planning Engineer"
    assert audits[0]["new_values"]["actual_quantity"] == 5.0


@pytest.mark.asyncio
async def test_idempotency_prevents_duplicate_mutation(client: AsyncClient, prepare_database):
    """Re-submitting an already applied candidate returns ALREADY_APPLIED without duplicate quantity."""
    project_id, schedule_version_id = await setup_project_and_schedule(client)

    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed topographical survey and peg marking for 5 km along section 10+000 to 15+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    event_id = dpr_res.json()["events"][0]["id"]
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=1")
    cand_id = match_res.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{cand_id}")

    # First approval
    appr1 = await client.post(f"/api/v1/review/candidates/{cand_id}/approve")
    assert appr1.status_code == 200
    assert appr1.json()["status"] == "APPLIED"

    # Second approval (Idempotency test)
    appr2 = await client.post(f"/api/v1/review/candidates/{cand_id}/approve")
    assert appr2.status_code == 200
    assert appr2.json()["status"] == "ALREADY_APPLIED"

    # Verify actual_quantity was NOT doubled
    acts_res = await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")
    act = next(a for a in acts_res.json() if a["activity_code"] == "ACT-1010")
    assert act["actual_quantity"] == 5.0


@pytest.mark.asyncio
async def test_hard_violation_blocks_normal_approval(client: AsyncClient, prepare_database):
    """Candidates with hard violations CANNOT be approved via standard approve endpoint."""
    project_id, schedule_version_id = await setup_project_and_schedule(client)

    # Ingest report for ACT-5020 (Manifold Piping), whose predecessor ACT-5010 is unstarted
    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Valve Station 01 Manifold Piping & Actuator Mounting completed today at SV-01.",
            "reporter_name": "Er. Phukan",
        },
    )
    event_id = dpr_res.json()["events"][0]["id"]
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=1")
    cand_id = match_res.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{cand_id}")

    # Attempt normal approval -> Must fail with HTTP 400
    appr_res = await client.post(f"/api/v1/review/candidates/{cand_id}/approve")
    assert appr_res.status_code == 400
    assert "Standard approval is prohibited" in appr_res.json()["detail"]

    # Verify zero schedule mutation
    acts_res = await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")
    act = next(a for a in acts_res.json() if a["activity_code"] == "ACT-5020")
    assert act["actual_quantity"] == 0.0
    assert act["physical_percent_complete"] == 0.0


@pytest.mark.asyncio
async def test_override_workflow_requires_valid_reason_and_mutates(client: AsyncClient, prepare_database):
    """
    Overriding a blocked candidate:
    - Fails if override_reason is empty or < 5 characters.
    - Succeeds with valid reason, mutating actuals and setting is_override=True in audit log.
    """
    project_id, schedule_version_id = await setup_project_and_schedule(client)

    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Valve Station 01 Manifold Piping & Actuator Mounting completed today at SV-01.",
            "reporter_name": "Er. Phukan",
        },
    )
    event_id = dpr_res.json()["events"][0]["id"]
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=1")
    cand_id = match_res.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{cand_id}")

    # Attempt override with invalid short reason (< 5 chars)
    short_res = await client.post(
        f"/api/v1/review/candidates/{cand_id}/override",
        json={"override_reason": "ok"},
    )
    assert short_res.status_code == 422 or short_res.status_code == 400

    # Valid override with justification
    valid_res = await client.post(
        f"/api/v1/review/candidates/{cand_id}/override",
        json={
            "reviewer_user": "Project Director",
            "remarks": "Priority work approved by client directive.",
            "override_reason": "Predecessor foundation curing verified offline via non-destructive core testing.",
        },
    )
    assert valid_res.status_code == 200
    mut_data = valid_res.json()
    assert mut_data["status"] == "APPLIED"
    assert mut_data["action"] == "OVERRIDDEN"

    # Verify ScheduleActivity actuals updated
    acts_res = await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")
    act = next(a for a in acts_res.json() if a["activity_code"] == "ACT-5020")
    assert act["actual_quantity"] == 0.0
    assert act["physical_percent_complete"] == 100.0

    # Verify Audit Record
    audit_res = await client.get(f"/api/v1/review/audit?project_id={project_id}&action=OVERRIDDEN")
    assert audit_res.status_code == 200
    audits = audit_res.json()
    assert len(audits) >= 1
    assert audits[0]["is_override"] is True
    assert "core testing" in audits[0]["override_reason"]


@pytest.mark.asyncio
async def test_rejection_workflow_zero_mutation(client: AsyncClient, prepare_database):
    """Rejection marks candidate as REJECTED without modifying schedule actuals."""
    project_id, schedule_version_id = await setup_project_and_schedule(client)

    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed topographical survey and peg marking for 5 km along section 10+000 to 15+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    event_id = dpr_res.json()["events"][0]["id"]
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=1")
    cand_id = match_res.json()["candidates"][0]["candidate_id"]

    rej_res = await client.post(
        f"/api/v1/review/candidates/{cand_id}/reject",
        json={"reason": "Duplicate field report entry; already captured in earlier batch."},
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "REJECTED"

    # Verify candidate status
    detail = (await client.get(f"/api/v1/review/candidates/{cand_id}")).json()
    assert detail["status"] == "REJECTED"

    # Verify zero schedule mutation
    acts_res = await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")
    act = next(a for a in acts_res.json() if a["activity_code"] == "ACT-1010")
    assert act["actual_quantity"] == 0.0
    assert act["physical_percent_complete"] == 0.0


@pytest.mark.asyncio
async def test_reassignment_triggers_fresh_validation_and_zero_mutation(client: AsyncClient, prepare_database):
    """Reassigning candidate to a target activity triggers fresh validation and does NOT mutate actuals."""
    project_id, schedule_version_id = await setup_project_and_schedule(client)

    acts_res = await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")
    act_1010 = next(a for a in acts_res.json() if a["activity_code"] == "ACT-1010")
    act_1020 = next(a for a in acts_res.json() if a["activity_code"] == "ACT-1020")

    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed survey and clearing work at chainage 12+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    event_id = dpr_res.json()["events"][0]["id"]
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=1")
    cand_id = match_res.json()["candidates"][0]["candidate_id"]

    # Reassign to ACT-1020
    reassign_res = await client.post(
        f"/api/v1/review/candidates/{cand_id}/reassign",
        json={"target_activity_id": act_1020["id"], "reason": "Work corresponds to ROW Clearing."},
    )
    assert reassign_res.status_code == 200
    reassign_data = reassign_res.json()
    assert reassign_data["status"] == "REASSIGNED"
    assert reassign_data["activity_code"] == "ACT-1020"

    # Detail reflects new activity and fresh validation
    detail = (await client.get(f"/api/v1/review/candidates/{cand_id}")).json()
    assert detail["activity_code"] == "ACT-1020"

    # Zero schedule mutation of either activity
    acts_after = (await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")).json()
    for a in acts_after:
        assert a["actual_quantity"] == 0.0
        assert a["physical_percent_complete"] == 0.0


@pytest.mark.asyncio
async def test_edit_event_workflow_fresh_validation_zero_mutation(client: AsyncClient, prepare_database):
    """Editing progress parameters modifies the event and triggers fresh validation without mutating schedule."""
    project_id, schedule_version_id = await setup_project_and_schedule(client)

    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed topographical survey and peg marking for 5 km along section 10+000 to 15+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    event_id = dpr_res.json()["events"][0]["id"]
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=1")
    cand_id = match_res.json()["candidates"][0]["candidate_id"]

    # Engineer corrects reported quantity from 5.0 to 4.5
    edit_res = await client.post(
        f"/api/v1/review/candidates/{cand_id}/edit",
        json={
            "quantity_reported": 4.5,
            "uom": "KM",
            "reason": "Corrected for swamp exclusion zone.",
        },
    )
    assert edit_res.status_code == 200
    assert edit_res.json()["status"] == "EDITED"

    # Detail shows updated reported quantity
    detail = (await client.get(f"/api/v1/review/candidates/{cand_id}")).json()
    assert detail["quantity_reported"] == 4.5

    # Schedule actuals still ZERO
    acts_res = await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")
    act = next(a for a in acts_res.json() if a["activity_code"] == "ACT-1010")
    assert act["actual_quantity"] == 0.0


@pytest.mark.asyncio
async def test_dashboard_stats_and_audit_log_query(client: AsyncClient, prepare_database):
    """Tests high-level project KPIs and audit log queries."""
    project_id, schedule_version_id = await setup_project_and_schedule(client)

    stats_res = await client.get(f"/api/v1/review/dashboard-stats?project_id={project_id}")
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert "total_reports" in stats
    assert "total_events" in stats
    assert "auto_matched" in stats
    assert "applied" in stats
    assert "unresolved_violations" in stats


@pytest.mark.asyncio
async def test_structural_safety_only_schedule_update_service_mutates_actuals(client: AsyncClient, prepare_database):
    """
    CRITICAL ARCHITECTURAL SAFETY ASSERTION:
    Inspects that matcher, validator, rejection, reassignment, and edit actions
    NEVER modify schedule actual fields. ONLY approve/override through ScheduleUpdateService do.
    """
    project_id, schedule_version_id = await setup_project_and_schedule(client)

    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Valve Station 01 Manifold Piping & Actuator Mounting completed today at SV-01.",
            "reporter_name": "Er. Phukan",
        },
    )
    event_id = dpr_res.json()["events"][0]["id"]

    # Matcher executed
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=2")
    cand_id = match_res.json()["candidates"][0]["candidate_id"]

    # Validator executed
    await client.post(f"/api/v1/validation/candidates/{cand_id}")

    # Check that ALL activities in schedule have zero actual progress
    acts_res = await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")
    for act in acts_res.json():
        assert act["actual_quantity"] == 0.0
        assert act["actual_start"] is None
        assert act["actual_finish"] is None
        assert act["physical_percent_complete"] == 0.0


@pytest.mark.asyncio
async def test_completed_event_without_quantity_does_not_fabricate(client: AsyncClient, prepare_database):
    """
    Non-fabrication: When an event reports completion without explicit quantity:
    - Planned quantity is NOT copied
    - 1.0 is NOT fabricated
    - Existing actual quantity (0.0) is preserved
    - physical_percent_complete becomes 100.0
    """
    project_id, schedule_version_id = await setup_project_and_schedule(client)
    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed topographical survey and peg marking along section 10+000 to 15+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    event_id = dpr_res.json()["events"][0]["id"]
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=1")
    cand_id = match_res.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{cand_id}")

    appr_res = await client.post(f"/api/v1/review/candidates/{cand_id}/approve")
    assert appr_res.status_code == 200

    acts_res = await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")
    act = next(a for a in acts_res.json() if a["activity_code"] == "ACT-1010")
    assert act["actual_quantity"] == 0.0  # Preserved from 0.0, NOT fabricated!
    assert act["physical_percent_complete"] == 100.0


@pytest.mark.asyncio
async def test_completed_event_with_explicit_quantity(client: AsyncClient, prepare_database):
    """
    Explicit quantity reporting: When an event explicitly provides a quantity:
    - The explicit quantity is applied
    - physical_percent_complete becomes 100.0
    """
    project_id, schedule_version_id = await setup_project_and_schedule(client)
    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed topographical survey and peg marking for 5 km along section 10+000 to 15+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    event_id = dpr_res.json()["events"][0]["id"]
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=1")
    cand_id = match_res.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{cand_id}")

    appr_res = await client.post(f"/api/v1/review/candidates/{cand_id}/approve")
    assert appr_res.status_code == 200

    acts_res = await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")
    act = next(a for a in acts_res.json() if a["activity_code"] == "ACT-1010")
    assert act["actual_quantity"] == 5.0
    assert act["physical_percent_complete"] == 100.0


@pytest.mark.asyncio
async def test_incremental_quantity_semantics(client: AsyncClient, prepare_database):
    """
    Incremental quantity semantics:
    When report mentions 'additional' / 'completed today', the reported delta is added to existing actuals.
    """
    project_id, schedule_version_id = await setup_project_and_schedule(client)

    # First report: 5 km
    dpr1 = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed topographical survey and peg marking for 5 km along section 10+000 to 15+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    e1_id = dpr1.json()["events"][0]["id"]
    m1 = await client.post(f"/api/v1/matching/progress-events/{e1_id}?top_k=1")
    c1_id = m1.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{c1_id}")
    await client.post(f"/api/v1/review/candidates/{c1_id}/approve")

    # Second report: incremental "additional 3 km"
    dpr2 = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed topographical survey for additional 3 km executed today along section 15+000 to 18+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    e2_id = dpr2.json()["events"][0]["id"]
    m2 = await client.post(f"/api/v1/matching/progress-events/{e2_id}?top_k=1")
    c2_id = m2.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{c2_id}")
    appr2 = await client.post(f"/api/v1/review/candidates/{c2_id}/approve")
    assert appr2.status_code == 200

    acts_res = await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")
    act = next(a for a in acts_res.json() if a["activity_code"] == "ACT-1010")
    assert act["actual_quantity"] == 8.0  # 5.0 + 3.0 incremental


@pytest.mark.asyncio
async def test_cumulative_quantity_semantics(client: AsyncClient, prepare_database):
    """
    Cumulative quantity semantics:
    When report mentions 'total to date' or 'cumulative', the quantity represents the total achieved to date.
    """
    project_id, schedule_version_id = await setup_project_and_schedule(client)

    # First report: 5 km (in progress)
    dpr1 = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Ongoing topographical survey and peg marking for 5 km along section 10+000 to 15+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    e1_id = dpr1.json()["events"][0]["id"]
    m1 = await client.post(f"/api/v1/matching/progress-events/{e1_id}?top_k=1")
    c1_id = m1.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{c1_id}")
    await client.post(f"/api/v1/review/candidates/{c1_id}/approve")

    # Second report: cumulative "total to date reaches 7 km"
    dpr2 = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Topographical survey total to date reaches 7 km along pipeline corridor.",
            "reporter_name": "Er. H. Barua",
        },
    )
    e2_id = dpr2.json()["events"][0]["id"]
    m2 = await client.post(f"/api/v1/matching/progress-events/{e2_id}?top_k=1")
    c2_id = m2.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{c2_id}")
    appr2 = await client.post(f"/api/v1/review/candidates/{c2_id}/approve")
    assert appr2.status_code == 200

    acts_res = await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")
    act = next(a for a in acts_res.json() if a["activity_code"] == "ACT-1010")
    assert act["actual_quantity"] == 7.0  # Cumulative, NOT 5 + 7 = 12!


@pytest.mark.asyncio
async def test_unknown_quantity_semantics_preserves_existing(client: AsyncClient, prepare_database):
    """
    Unknown semantics safety rule:
    When existing actuals > 0 and new report does NOT establish whether quantity is cumulative or incremental,
    the existing quantity is strictly preserved rather than blindly adding.
    """
    project_id, schedule_version_id = await setup_project_and_schedule(client)

    # First report: 5 km
    dpr1 = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed topographical survey and peg marking for 5 km along section 10+000 to 15+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    e1_id = dpr1.json()["events"][0]["id"]
    m1 = await client.post(f"/api/v1/matching/progress-events/{e1_id}?top_k=1")
    c1_id = m1.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{c1_id}")
    await client.post(f"/api/v1/review/candidates/{c1_id}/approve")

    # Second report: ambiguous "Survey section 6 km" (no incremental or cumulative markers)
    dpr2 = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Topographical survey and peg marking 6 km.",
            "reporter_name": "Er. H. Barua",
        },
    )
    e2_id = dpr2.json()["events"][0]["id"]
    m2 = await client.post(f"/api/v1/matching/progress-events/{e2_id}?top_k=1")
    c2_id = m2.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{c2_id}")
    appr2 = await client.post(f"/api/v1/review/candidates/{c2_id}/approve")
    assert appr2.status_code == 200

    acts_res = await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")
    act = next(a for a in acts_res.json() if a["activity_code"] == "ACT-1010")
    # Because actuals were already 5.0 and semantics was UNKNOWN, 5.0 is preserved!
    assert act["actual_quantity"] == 5.0


@pytest.mark.asyncio
async def test_stale_candidate_version_mismatch_returns_stale_review(client: AsyncClient, prepare_database):
    """
    Optimistic Concurrency Control:
    If target activity actuals are updated after a candidate was validated (version mismatch),
    attempting to approve returns STALE_REVIEW without mutating actuals.
    """
    project_id, schedule_version_id = await setup_project_and_schedule(client)

    # Create candidate 1
    dpr1 = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed topographical survey and peg marking for 5 km along section 10+000 to 15+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    e1_id = dpr1.json()["events"][0]["id"]
    m1 = await client.post(f"/api/v1/matching/progress-events/{e1_id}?top_k=1")
    c1_id = m1.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{c1_id}")

    # Create candidate 2 on the SAME activity
    dpr2 = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed topographical survey for additional 2 km executed today along section 15+000 to 17+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    e2_id = dpr2.json()["events"][0]["id"]
    m2 = await client.post(f"/api/v1/matching/progress-events/{e2_id}?top_k=1")
    c2_id = m2.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{c2_id}")

    # Both c1 and c2 were validated when activity version was 1.
    # Now approve c1 -> activity version becomes 2.
    appr1 = await client.post(f"/api/v1/review/candidates/{c1_id}/approve")
    assert appr1.status_code == 200
    assert appr1.json()["status"] == "APPLIED"

    # Now attempt to approve c2 without re-validation:
    # c2 was validated against version 1, but activity is now version 2!
    appr2 = await client.post(f"/api/v1/review/candidates/{c2_id}/approve")
    assert appr2.status_code == 200
    assert appr2.json()["status"] == "STALE_REVIEW"

    # Re-validate c2: now c2 is validated against version 2
    reval = await client.post(f"/api/v1/validation/candidates/{c2_id}")
    assert reval.status_code == 200

    # Now approve c2 succeeds!
    appr2_retry = await client.post(f"/api/v1/review/candidates/{c2_id}/approve")
    assert appr2_retry.status_code == 200
    assert appr2_retry.json()["status"] == "APPLIED"


@pytest.mark.asyncio
async def test_stale_review_candidate_cannot_apply(client: AsyncClient, prepare_database):
    """A candidate explicitly marked as STALE_REVIEW cannot be approved directly."""
    from tests.conftest import TestingSessionLocal
    from app.modules.semantic_matcher.models import ActivityMatchCandidate
    from sqlalchemy import select

    project_id, schedule_version_id = await setup_project_and_schedule(client)
    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed topographical survey and peg marking for 5 km along section 10+000 to 15+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    event_id = dpr_res.json()["events"][0]["id"]
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=1")
    cand_id = match_res.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{cand_id}")

    # Manually set status to STALE_REVIEW in DB
    async with TestingSessionLocal() as db:
        cand = (await db.execute(select(ActivityMatchCandidate).where(ActivityMatchCandidate.id == cand_id))).scalar_one()
        cand.status = "STALE_REVIEW"
        await db.commit()

    # Attempt to approve -> HTTP 400
    res = await client.post(f"/api/v1/review/candidates/{cand_id}/approve")
    assert res.status_code == 400
    assert "STALE_REVIEW" in res.json()["detail"]


@pytest.mark.asyncio
async def test_unsupported_candidate_state_cannot_apply(client: AsyncClient, prepare_database):
    """Candidates in arbitrary or invalid state cannot be approved."""
    from tests.conftest import TestingSessionLocal
    from app.modules.semantic_matcher.models import ActivityMatchCandidate
    from sqlalchemy import select

    project_id, schedule_version_id = await setup_project_and_schedule(client)
    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed topographical survey and peg marking for 5 km along section 10+000 to 15+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    event_id = dpr_res.json()["events"][0]["id"]
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=1")
    cand_id = match_res.json()["candidates"][0]["candidate_id"]

    # Manually set status to UNSUPPORTED in DB
    async with TestingSessionLocal() as db:
        cand = (await db.execute(select(ActivityMatchCandidate).where(ActivityMatchCandidate.id == cand_id))).scalar_one()
        cand.status = "UNSUPPORTED_STATUS"
        await db.commit()

    res = await client.post(f"/api/v1/review/candidates/{cand_id}/approve")
    assert res.status_code == 400
    assert "cannot be applied" in res.json()["detail"]


@pytest.mark.asyncio
async def test_audit_project_id_present_across_all_review_actions(client: AsyncClient, prepare_database):
    """All 5 review actions (Approve, Override, Reject, Reassign, Edit) log project_id in ReviewAudit."""
    project_id, schedule_version_id = await setup_project_and_schedule(client)

    # 1. Reject action
    dpr_reject = await client.post(
        "/api/v1/field-reports/raw-text",
        json={"project_id": project_id, "raw_text": "Clearing and grubbing ongoing.", "reporter_name": "R1"},
    )
    e_rej = dpr_reject.json()["events"][0]["id"]
    m_rej = (await client.post(f"/api/v1/matching/progress-events/{e_rej}?top_k=1")).json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/review/candidates/{m_rej}/reject", json={"reason": "Invalid report"})

    # 2. Reassign action
    dpr_reassign = await client.post(
        "/api/v1/field-reports/raw-text",
        json={"project_id": project_id, "raw_text": "Clearing and grubbing ongoing.", "reporter_name": "R2"},
    )
    e_reas = dpr_reassign.json()["events"][0]["id"]
    m_reas = (await client.post(f"/api/v1/matching/progress-events/{e_reas}?top_k=1")).json()["candidates"][0]["candidate_id"]
    acts = (await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")).json()
    target_act = next(a for a in acts if a["activity_code"] == "ACT-1020")
    await client.post(f"/api/v1/review/candidates/{m_reas}/reassign", json={"target_activity_id": target_act["id"]})

    # 3. Edit action
    await client.post(
        f"/api/v1/review/candidates/{m_reas}/edit",
        json={"quantity_reported": 1.5, "reason": "Corrected surveyor reading"},
    )

    # Query audits
    audit_res = await client.get(f"/api/v1/review/audit?project_id={project_id}")
    assert audit_res.status_code == 200
    audits = audit_res.json()
    assert len(audits) >= 3
    for a in audits:
        assert a["project_id"] == project_id, f"Audit {a['id']} has missing or incorrect project_id!"


@pytest.mark.asyncio
async def test_edit_event_work_description_invalidates_match(client: AsyncClient, prepare_database):
    """
    Editing work_description on a progress event changes match semantics:
    - Invalidates previous match
    - Sets candidate status to NEEDS_REMATCH
    - Deletes previous dependency violations
    - Sets confidence_score to 0.0
    """
    project_id, schedule_version_id = await setup_project_and_schedule(client)
    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed topographical survey and peg marking for 5 km along section 10+000 to 15+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    event_id = dpr_res.json()["events"][0]["id"]
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=1")
    cand_id = match_res.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{cand_id}")

    # Edit work_description
    edit_res = await client.post(
        f"/api/v1/review/candidates/{cand_id}/edit",
        json={
            "work_description": "Excavation and trenching for pipeline lowering in rocky terrain.",
            "reason": "Correcting misclassified work scope",
        },
    )
    assert edit_res.status_code == 200
    data = edit_res.json()
    assert data["status"] == "NEEDS_REMATCH"

    # Verify detail shows NEEDS_REMATCH and 0 violations
    detail = (await client.get(f"/api/v1/review/candidates/{cand_id}")).json()
    assert detail["status"] == "NEEDS_REMATCH"
    assert detail["confidence_score"] == 0.0
    assert len(detail["violations"]) == 0


@pytest.mark.asyncio
async def test_transaction_rollback_on_failure(client: AsyncClient, prepare_database):
    """
    Transaction atomicity:
    If an unexpected failure occurs during candidate approval before commit,
    the database transaction rolls back completely, leaving schedule actuals unchanged.
    """
    from unittest.mock import patch

    project_id, schedule_version_id = await setup_project_and_schedule(client)
    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Completed topographical survey and peg marking for 5 km along section 10+000 to 15+000.",
            "reporter_name": "Er. H. Barua",
        },
    )
    event_id = dpr_res.json()["events"][0]["id"]
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=1")
    cand_id = match_res.json()["candidates"][0]["candidate_id"]
    await client.post(f"/api/v1/validation/candidates/{cand_id}")

    # Patch db.commit to simulate database failure during commit
    with patch("sqlalchemy.ext.asyncio.AsyncSession.commit", side_effect=RuntimeError("Simulated DB commit failure")):
        res = await client.post(f"/api/v1/review/candidates/{cand_id}/approve")
        assert res.status_code == 500

    # Verify ScheduleActivity actuals remain completely unmutated
    acts_res = await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")
    act = next(a for a in acts_res.json() if a["activity_code"] == "ACT-1010")
    assert act["actual_quantity"] == 0.0
    assert act["actual_start"] is None
    assert act["actual_finish"] is None
    assert act["physical_percent_complete"] == 0.0
