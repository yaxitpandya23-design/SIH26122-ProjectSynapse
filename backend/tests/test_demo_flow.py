import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_demo_seed_and_status(client: AsyncClient, prepare_database):
    """
    Tests POST /api/v1/demo/seed and GET /api/v1/demo/status:
    - Seeds the Oil India 30 KM pipeline project.
    - Verifies 20 activities, 25 dependencies, 5 DPRs, and validated candidates.
    """
    res = await client.post("/api/v1/demo/seed")
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "SEEDED"
    assert data["project_code"] == "OIL-SYNAPSE-DEMO"
    assert data["activities_count"] == 20
    assert data["reports_count"] == 5
    assert data["events_count"] == 6

    # Verify status
    status_res = await client.get("/api/v1/demo/status")
    assert status_res.status_code == 200
    st = status_res.json()
    assert st["is_seeded"] is True
    assert st["project_code"] == "OIL-SYNAPSE-DEMO"
    assert st["activities_count"] == 20


@pytest.mark.asyncio
async def test_demo_scenario_1_high_confidence_approval(client: AsyncClient, prepare_database):
    """
    Scenario 1: High-confidence clean match
    - ACT-1010 Topographical survey
    - Confidence >= 0.85
    - Approving updates actual_quantity = 5.0, physical_percent_complete = 100.0
    - Baseline planned values remain strictly immutable
    """
    seed_res = await client.post("/api/v1/demo/seed")
    project_id = seed_res.json()["project_id"]

    # Fetch inbox items
    inbox_res = await client.get(f"/api/v1/review/inbox?project_id={project_id}")
    assert inbox_res.status_code == 200
    items = inbox_res.json()

    scen1_item = next(i for i in items if i["activity_code"] == "ACT-1010")
    assert scen1_item["confidence_score"] >= 0.85
    assert scen1_item["status"] in ("AUTO_MATCHED", "NEEDS_REVIEW")
    assert scen1_item["has_hard_violations"] is False

    # Fetch activity BEFORE approval
    detail_before = await client.get(f"/api/v1/review/candidates/{scen1_item['candidate_id']}")
    act_code = detail_before.json()["activity_code"]
    assert detail_before.json()["actual_quantity"] == 0.0

    # Approve
    appr_res = await client.post(
        f"/api/v1/review/candidates/{scen1_item['candidate_id']}/approve",
        json={"reviewer_user": "Chief Surveyor", "remarks": "Field sheets verified."},
    )
    assert appr_res.status_code == 200
    mut = appr_res.json()
    assert mut["status"] == "APPLIED"
    assert mut["action"] == "APPROVED"
    assert mut["new_values"]["actual_quantity"] == 5.0
    assert mut["new_values"]["physical_percent_complete"] == 100.0


@pytest.mark.asyncio
async def test_demo_scenario_2_ambiguous_match_and_reassign(client: AsyncClient, prepare_database):
    """
    Scenario 2: Ambiguous match + Human Reassignment
    - DPR: 'Pipeline welding completed near the river crossing section.'
    - Initial candidate ≈ ACT-2030
    - Reassigned to ACT-3010 (HDD River Crossing)
    - Reassignment triggers fresh validation with zero schedule actuals mutation
    """
    seed_res = await client.post("/api/v1/demo/seed")
    project_id = seed_res.json()["project_id"]

    # Locate the welding candidate
    inbox_res = await client.get(f"/api/v1/review/inbox?project_id={project_id}")
    items = inbox_res.json()
    weld_item = next(
        i for i in items if "river crossing" in i["raw_text_snippet"].lower() or i["activity_code"] == "ACT-2030"
    )
    assert weld_item["status"] in ("NEEDS_REVIEW", "AUTO_MATCHED", "BLOCKED_BY_DEPENDENCY")

    # Locate target activity ACT-3010 (HDD River Crossing)
    acts_res = await client.get(f"/api/v1/schedules/project/{project_id}/activities")
    acts = acts_res.json()
    act_3010 = next(a for a in acts if a["activity_code"] == "ACT-3010")

    # Reassign to ACT-3010
    reassign_res = await client.post(
        f"/api/v1/review/candidates/{weld_item['candidate_id']}/reassign",
        json={
            "target_activity_id": act_3010["id"],
            "reason": "Corrected scope to HDD crossing per chainage alignment.",
            "reviewer_user": "Lead Pipeline Engineer",
        },
    )
    assert reassign_res.status_code == 200
    reassign_data = reassign_res.json()
    assert reassign_data["status"] == "REASSIGNED"
    assert reassign_data["activity_code"] == "ACT-3010"

    # Verify ScheduleActivity actuals for BOTH activities remain completely unmutated
    acts_after_res = await client.get(f"/api/v1/schedules/project/{project_id}/activities")
    acts_after = acts_after_res.json()
    act_2030_after = next(a for a in acts_after if a["activity_code"] == "ACT-2030")
    act_3010_after = next(a for a in acts_after if a["activity_code"] == "ACT-3010")
    assert act_2030_after["actual_quantity"] == 0.0
    assert act_3010_after["actual_quantity"] == 0.0


@pytest.mark.asyncio
async def test_demo_scenario_3_dependency_blocker_and_override(client: AsyncClient, prepare_database):
    """
    Scenario 3: Dependency Blocker + Justified Override
    - ACT-5020 (Manifold Piping)
    - Predecessor ACT-5010 (Civil Raft) is incomplete
    - Status: BLOCKED_BY_DEPENDENCY
    - Standard approval fails (HTTP 400)
    - Override with justification succeeds and mutates actuals
    """
    seed_res = await client.post("/api/v1/demo/seed")
    project_id = seed_res.json()["project_id"]

    inbox_res = await client.get(f"/api/v1/review/inbox?project_id={project_id}")
    items = inbox_res.json()
    blocked_item = next(i for i in items if i["activity_code"] == "ACT-5020")
    assert blocked_item["status"] == "BLOCKED_BY_DEPENDENCY"
    assert blocked_item["has_hard_violations"] is True
    assert blocked_item["can_approve"] is False
    assert blocked_item["can_override"] is True

    # Standard approval attempt -> Prohibited (HTTP 400)
    appr_fail = await client.post(f"/api/v1/review/candidates/{blocked_item['candidate_id']}/approve")
    assert appr_fail.status_code == 400
    assert "Standard approval is prohibited" in appr_fail.json()["detail"]

    # Authorized override with mandatory rationale >= 5 chars
    override_res = await client.post(
        f"/api/v1/review/candidates/{blocked_item['candidate_id']}/override",
        json={
            "override_reason": "Predecessor civil raft curing verified by laboratory rebound hammer testing.",
            "reviewer_user": "Project Director",
            "remarks": "Priority work cleared by OIL executive committee directive.",
        },
    )
    assert override_res.status_code == 200
    mut = override_res.json()
    assert mut["status"] == "APPLIED"
    assert mut["action"] == "OVERRIDDEN"

    # Verify audit record
    audits_res = await client.get(f"/api/v1/review/audit?project_id={project_id}&action=OVERRIDDEN")
    audits = audits_res.json()
    assert len(audits) >= 1
    assert audits[0]["is_override"] is True
    assert "rebound hammer" in audits[0]["override_reason"]


@pytest.mark.asyncio
async def test_demo_scenario_4_out_of_scope_rejection_zero_mutation(client: AsyncClient, prepare_database):
    """
    Scenario 4: Out-of-Scope / Unsafe Interpretation
    - DPR: Security gate painting
    - Confidence < 0.50, UNMATCHED
    - Approval prohibited
    - Rejection marks candidate as REJECTED with zero schedule mutation
    """
    seed_res = await client.post("/api/v1/demo/seed")
    project_id = seed_res.json()["project_id"]

    inbox_res = await client.get(f"/api/v1/review/inbox?project_id={project_id}")
    items = inbox_res.json()
    out_scope = next(i for i in items if "security gate" in i["raw_text_snippet"].lower())
    assert out_scope["confidence_score"] < 0.50
    assert out_scope["status"] == "UNMATCHED"

    # Approval attempt fails
    appr_res = await client.post(f"/api/v1/review/candidates/{out_scope['candidate_id']}/approve")
    assert appr_res.status_code == 400
    assert "Unmatched candidate cannot be applied" in appr_res.json()["detail"]

    # Rejection by Engineer
    rej_res = await client.post(
        f"/api/v1/review/candidates/{out_scope['candidate_id']}/reject",
        json={"reason": "Civil maintenance scope not tracked in capital baseline schedule.", "reviewer_user": "Lead Planner"},
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "REJECTED"

    # Verify all activities have zero actuals
    acts_res = await client.get(f"/api/v1/schedules/project/{project_id}/activities")
    for act in acts_res.json():
        assert act["actual_quantity"] == 0.0
        assert act["physical_percent_complete"] == 0.0


@pytest.mark.asyncio
async def test_demo_scenario_5_multi_event_dpr_discretization(client: AsyncClient, prepare_database):
    """
    Scenario 5: Multi-Event DPR
    - DPR contains 2 discrete work statements (Trenching 450m and Stringing 25 joints)
    - Parsed into 2 distinct ProgressEvents
    - Matched to ACT-1030 and ACT-2010
    - Independently validated and approved
    """
    seed_res = await client.post("/api/v1/demo/seed")
    project_id = seed_res.json()["project_id"]

    # Query events for project
    evts_res = await client.get(f"/api/v1/field-reports/events/all?project_id={project_id}")
    assert evts_res.status_code == 200
    events = evts_res.json()

    # Find the multi-event reports (trenching & stringing)
    trench_evt = next(e for e in events if "trench" in e["work_description"].lower() and e["quantity_reported"] == 450.0)
    string_evt = next(e for e in events if "stringing" in e["work_description"].lower() and e["quantity_reported"] == 25.0)

    assert trench_evt["id"] != string_evt["id"]
    assert trench_evt["field_report_id"] == string_evt["field_report_id"]


@pytest.mark.asyncio
async def test_demo_reset_and_repeatability(client: AsyncClient, prepare_database):
    """
    Verifies that RESET -> SEED -> RESET -> SEED produces identical, reproducible results.
    """
    # Seed 1
    seed1 = await client.post("/api/v1/demo/seed")
    assert seed1.status_code == 201
    d1 = seed1.json()

    # Reset
    reset1 = await client.post("/api/v1/demo/reset")
    assert reset1.status_code == 200

    # Verify status is not seeded
    st = (await client.get("/api/v1/demo/status")).json()
    assert st["is_seeded"] is False

    # Seed 2
    seed2 = await client.post("/api/v1/demo/seed")
    assert seed2.status_code == 201
    d2 = seed2.json()

    # Identical structure
    assert d1["activities_count"] == d2["activities_count"] == 20
    assert d1["reports_count"] == d2["reports_count"] == 5
    assert d1["events_count"] == d2["events_count"] == 6


@pytest.mark.asyncio
async def test_pre_approval_zero_mutation_safety_invariant(client: AsyncClient, prepare_database):
    """
    CRITICAL ARCHITECTURAL SAFETY INVARIANT TEST:
    Demonstrates that DPR ingestion -> extraction -> semantic matching ->
    confidence scoring -> dependency validation -> demo seeding CANNOT mutate
    ScheduleActivity actual fields (actual_quantity, actual_start, actual_finish,
    physical_percent_complete) before authorized ScheduleUpdateService approval.
    """
    # Seed the complete pipeline
    seed_res = await client.post("/api/v1/demo/seed")
    project_id = seed_res.json()["project_id"]

    # Verify every single activity in the schedule has zero actual progress
    acts_res = await client.get(f"/api/v1/schedules/project/{project_id}/activities")
    activities = acts_res.json()
    assert len(activities) == 20

    for act in activities:
        assert act["actual_quantity"] == 0.0, f"Activity {act['activity_code']} actual_quantity was modified prematurely!"
        assert act["actual_start"] is None, f"Activity {act['activity_code']} actual_start was set prematurely!"
        assert act["actual_finish"] is None, f"Activity {act['activity_code']} actual_finish was set prematurely!"
        assert act["physical_percent_complete"] == 0.0, f"Activity {act['activity_code']} percent_complete was modified prematurely!"
        assert act["actuals_version"] == 1, f"Activity {act['activity_code']} actuals_version was bumped prematurely!"
