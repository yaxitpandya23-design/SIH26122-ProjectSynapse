import pytest
from datetime import date, timedelta
from pathlib import Path
from httpx import AsyncClient
from sqlalchemy import select

from app.modules.dependency_validator.graph import ScheduleDependencyGraph
from app.modules.dependency_validator.rules import (
    validate_predecessors_complete,
    validate_sequence_and_lags,
    validate_quantity_overrun,
    validate_critical_path_impact,
    validate_graph_acyclic,
)
from app.modules.schedules.models import ScheduleActivity

SAMPLE_CSV_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "sample_data"
    / "schedules"
    / "oil_india_pipeline_sample.csv"
)


def test_fs_incomplete_predecessor_hard_violation():
    pred = {
        "id": "pred-1",
        "activity_code": "ACT-1010",
        "name": "Survey",
        "actual_finish": None,
        "physical_percent_complete": 40.0,
    }
    succ = {
        "id": "succ-1",
        "activity_code": "ACT-1020",
        "name": "ROW Clearing",
    }
    event = {"status_claim": "IN_PROGRESS"}

    graph = ScheduleDependencyGraph(
        activities=[pred, succ],
        dependencies=[{"predecessor_id": "pred-1", "successor_id": "succ-1", "dependency_type": "FS", "lag_days": 0}],
    )

    violations = validate_predecessors_complete(succ, event, graph)
    assert len(violations) == 1
    assert violations[0].violation_type == "PREDECESSOR_INCOMPLETE"
    assert violations[0].severity == "HARD_VIOLATION"
    assert "ACT-1010" in violations[0].description


def test_fs_completed_predecessor_passes():
    pred = {
        "id": "pred-1",
        "activity_code": "ACT-1010",
        "name": "Survey",
        "actual_finish": date(2026, 10, 7),
        "physical_percent_complete": 100.0,
    }
    succ = {
        "id": "succ-1",
        "activity_code": "ACT-1020",
        "name": "ROW Clearing",
    }
    event = {"status_claim": "IN_PROGRESS"}

    graph = ScheduleDependencyGraph(
        activities=[pred, succ],
        dependencies=[{"predecessor_id": "pred-1", "successor_id": "succ-1", "dependency_type": "FS", "lag_days": 0}],
    )

    violations = validate_predecessors_complete(succ, event, graph)
    assert len(violations) == 0


def test_ss_incomplete_predecessor_blocks():
    pred = {
        "id": "pred-1",
        "activity_code": "ACT-1020",
        "name": "ROW Clearing",
        "actual_start": None,
        "physical_percent_complete": 0.0,
    }
    succ = {
        "id": "succ-1",
        "activity_code": "ACT-1030",
        "name": "Trenching",
    }
    event = {"status_claim": "STARTED"}

    graph = ScheduleDependencyGraph(
        activities=[pred, succ],
        dependencies=[{"predecessor_id": "pred-1", "successor_id": "succ-1", "dependency_type": "SS", "lag_days": 5}],
    )

    violations = validate_predecessors_complete(succ, event, graph)
    assert len(violations) == 1
    assert violations[0].violation_type == "PREDECESSOR_INCOMPLETE"
    assert violations[0].severity == "HARD_VIOLATION"


def test_out_of_sequence_date_violation():
    pred = {
        "id": "pred-1",
        "activity_code": "ACT-1010",
        "name": "Survey",
        "actual_finish": date(2026, 10, 15),
    }
    succ = {
        "id": "succ-1",
        "activity_code": "ACT-1020",
        "name": "ROW Clearing",
    }
    # Event reported on Oct 10, which precedes predecessor finish on Oct 15
    event = {"event_date": date(2026, 10, 10)}

    graph = ScheduleDependencyGraph(
        activities=[pred, succ],
        dependencies=[{"predecessor_id": "pred-1", "successor_id": "succ-1", "dependency_type": "FS", "lag_days": 0}],
    )

    violations = validate_sequence_and_lags(succ, event, graph)
    assert len(violations) == 1
    assert violations[0].violation_type == "OUT_OF_SEQUENCE"
    assert violations[0].severity == "HARD_VIOLATION"


def test_quantity_overrun_violations():
    act = {
        "id": "act-1",
        "activity_code": "ACT-2010",
        "planned_quantity": 100.0,
        "actual_quantity": 10.0,
        "uom": "JOINTS",
    }

    # Severe overrun: 10 + 120 = 130 joints (> 15% overrun) -> HARD_VIOLATION
    event_severe = {"quantity_reported": 120.0}
    violations_severe = validate_quantity_overrun(act, event_severe)
    assert len(violations_severe) == 1
    assert violations_severe[0].violation_type == "QUANTITY_OVERRUN"
    assert violations_severe[0].severity == "HARD_VIOLATION"

    # Moderate overrun: 10 + 95 = 105 joints (5% overrun) -> SOFT_WARNING
    event_mild = {"quantity_reported": 95.0}
    violations_mild = validate_quantity_overrun(act, event_mild)
    assert len(violations_mild) == 1
    assert violations_mild[0].violation_type == "QUANTITY_OVERRUN"
    assert violations_mild[0].severity == "SOFT_WARNING"

    # Normal within budget: 10 + 50 = 60 joints -> No violation
    event_ok = {"quantity_reported": 50.0}
    violations_ok = validate_quantity_overrun(act, event_ok)
    assert len(violations_ok) == 0


@pytest.mark.asyncio
async def test_end_to_end_validation_api_and_decision_blocking(client: AsyncClient, prepare_database):
    """
    Tests full pipeline from Project & Schedule Ingestion -> DPR -> Matching -> Validation.
    Demonstrates that high semantic confidence does NOT auto-approve if predecessor is incomplete.
    """
    # 1. Create Project and Upload Schedule
    proj_res = await client.post(
        "/api/v1/schedules/projects",
        json={"name": "Pipeline Validation Project", "code": "VALID-01", "client_name": "Oil India Limited"}
    )
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    csv_bytes = SAMPLE_CSV_PATH.read_bytes()
    upload_res = await client.post(
        "/api/v1/schedules/upload-csv",
        data={"project_id": project_id, "version_label": "Baseline Rev 0"},
        files={"file": ("schedule.csv", csv_bytes, "text/csv")}
    )
    assert upload_res.status_code == 200

    # 2. Ingest Scenario A2: Complete Milestone Scope for ACT-5020
    # In the schedule, ACT-5020 depends on ACT-5010 (Civil Raft casting).
    # Since ACT-5010 has not completed yet, ACT-5020 has an incomplete predecessor!
    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Valve station manifold piping and actuator mounting completed today at SV-01.",
            "reporter_name": "Er. Phukan"
        }
    )
    assert dpr_res.status_code == 201
    event_id = dpr_res.json()["events"][0]["id"]

    # 3. Match candidate
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=5")
    assert match_res.status_code == 200
    top_cand = match_res.json()["candidates"][0]
    candidate_id = top_cand["candidate_id"]
    assert top_cand["activity_code"] == "ACT-5020"
    assert top_cand["confidence_score"] >= 0.85

    # 4. Run Validation on the candidate
    val_res = await client.post(f"/api/v1/validation/candidates/{candidate_id}")
    assert val_res.status_code == 200
    val_data = val_res.json()

    # Even though confidence is ~0.96, ACT-5010 is incomplete!
    # Validation MUST flag a HARD_VIOLATION and change decision to BLOCKED_BY_DEPENDENCY!
    assert val_data["has_hard_violations"] is True
    assert val_data["final_decision"] == "BLOCKED_BY_DEPENDENCY"
    assert len(val_data["violations"]) > 0
    assert any(v["violation_type"] == "PREDECESSOR_INCOMPLETE" for v in val_data["violations"])
    assert any("ACT-5010" in v["description"] for v in val_data["violations"])

    # 5. Retrieve validation by GET
    get_val_res = await client.get(f"/api/v1/validation/candidates/{candidate_id}")
    assert get_val_res.status_code == 200
    assert get_val_res.json()["final_decision"] == "BLOCKED_BY_DEPENDENCY"

    # 6. List Violations Endpoint
    viols_res = await client.get(f"/api/v1/validation/violations?project_id={project_id}&severity=HARD_VIOLATION")
    assert viols_res.status_code == 200
    viols_list = viols_res.json()
    assert len(viols_list) >= 1
    assert viols_list[0]["severity"] == "HARD_VIOLATION"

    # 7. Get Project Graph Endpoint
    graph_res = await client.get(f"/api/v1/validation/projects/{project_id}/graph")
    assert graph_res.status_code == 200
    graph_data = graph_res.json()
    assert len(graph_data["nodes"]) == 20
    assert len(graph_data["edges"]) == 25
    assert graph_data["has_cycles"] is False
    assert len(graph_data["critical_path_activities"]) > 0


@pytest.mark.asyncio
async def test_validation_engine_preserves_schedule_immutability(client: AsyncClient, prepare_database):
    """
    Strict Architectural Safety Invariant:
    Validation engine evaluates constraints without modifying any actual values in schedule_activities.
    """
    proj_res = await client.post(
        "/api/v1/schedules/projects",
        json={"name": "Immutability Project", "code": "IMMUT-01", "client_name": "Oil India Limited"}
    )
    project_id = proj_res.json()["id"]
    csv_bytes = SAMPLE_CSV_PATH.read_bytes()
    upload_res = await client.post(
        "/api/v1/schedules/upload-csv",
        data={"project_id": project_id, "version_label": "Baseline Rev 0"},
        files={"file": ("schedule.csv", csv_bytes, "text/csv")}
    )
    assert upload_res.status_code == 200
    schedule_version_id = upload_res.json()["schedule_version_id"]

    dpr_res = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Valve station manifold piping and actuator mounting completed today at SV-01.",
            "reporter_name": "Er. Phukan"
        }
    )
    event_id = dpr_res.json()["events"][0]["id"]
    match_res = await client.post(f"/api/v1/matching/progress-events/{event_id}?top_k=3")
    cand_id = match_res.json()["candidates"][0]["candidate_id"]

    # Run validation
    await client.post(f"/api/v1/validation/candidates/{cand_id}")

    # Inspect all activities via API to ensure ZERO actual progress was committed
    acts_res = await client.get(f"/api/v1/schedules/{schedule_version_id}/activities")
    assert acts_res.status_code == 200
    acts = acts_res.json()
    assert len(acts) > 0
    for act in acts:
        assert act["actual_quantity"] == 0.0, f"Activity {act['activity_code']} actual_quantity was modified!"
        assert act["actual_start"] is None, f"Activity {act['activity_code']} actual_start was modified!"
        assert act["actual_finish"] is None, f"Activity {act['activity_code']} actual_finish was modified!"
        assert act["physical_percent_complete"] == 0.0, f"Activity {act['activity_code']} percent_complete was modified!"
