import pytest
from pathlib import Path
from httpx import AsyncClient

SAMPLE_CSV_PATH = Path(__file__).resolve().parent.parent.parent / "sample_data" / "schedules" / "oil_india_pipeline_sample.csv"


@pytest.mark.asyncio
async def test_matching_api_endpoints_and_demo_scenarios(client: AsyncClient, prepare_database):
    # 1. Setup Project & Upload Oil India Schedule
    proj_res = await client.post(
        "/api/v1/schedules/projects",
        json={
            "name": "Duliajan-Numaligarh 16-inch Pipeline",
            "code": "DNPL-MATCH-TEST",
            "client_name": "Oil India Limited"
        }
    )
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    # Upload schedule
    csv_bytes = SAMPLE_CSV_PATH.read_bytes()
    upload_res = await client.post(
        "/api/v1/schedules/upload-csv",
        data={"project_id": project_id, "version_label": "Baseline Rev 0"},
        files={"file": ("oil_india_pipeline_sample.csv", csv_bytes, "text/csv")}
    )
    assert upload_res.status_code == 200

    # 2. Test Scenario A — Partial Scope Match / Needs Review
    # "Spool erection for Line 24 near Pump House completed today at SV-01."
    dpr_a = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Spool erection for Line 24 near Pump House completed today at SV-01.",
            "reporter_name": "Er. Baruah"
        }
    )
    assert dpr_a.status_code == 201
    events_a = dpr_a.json()["events"]
    assert len(events_a) > 0
    event_a_id = events_a[0]["id"]

    match_res_a = await client.post(f"/api/v1/matching/progress-events/{event_a_id}?top_k=5")
    assert match_res_a.status_code == 200
    data_a = match_res_a.json()
    assert len(data_a["candidates"]) > 0
    # Ranked candidate #1 is ACT-5020, but gated to NEEDS_REVIEW due to partial scope and Line 24/Pump House
    top_cand_a = data_a["candidates"][0]
    assert top_cand_a["activity_code"] == "ACT-5020"
    assert 0.50 <= top_cand_a["confidence_score"] <= 0.8499
    assert top_cand_a["decision_status"] == "NEEDS_REVIEW"
    assert len(top_cand_a["matching_reasons"]) > 0
    assert any("partial scope" in m.lower() for m in top_cand_a["mismatch_reasons"])

    # 2b. Test Scenario A2 — Full Milestone Scope Auto-Match
    # "Valve station manifold piping and actuator mounting completed today at SV-01."
    dpr_a2 = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Valve station manifold piping and actuator mounting completed today at SV-01.",
            "reporter_name": "Er. Baruah"
        }
    )
    assert dpr_a2.status_code == 201
    events_a2 = dpr_a2.json()["events"]
    assert len(events_a2) > 0
    event_a2_id = events_a2[0]["id"]

    match_res_a2 = await client.post(f"/api/v1/matching/progress-events/{event_a2_id}?top_k=5")
    assert match_res_a2.status_code == 200
    data_a2 = match_res_a2.json()
    top_cand_a2 = data_a2["candidates"][0]
    assert top_cand_a2["activity_code"] == "ACT-5020"
    assert top_cand_a2["confidence_score"] >= 0.85
    assert top_cand_a2["decision_status"] == "AUTO_MATCHED"

    # 3. Test Scenario B — Ambiguous Candidate Handling
    # "Pipeline welding completed near the crossing."
    dpr_b = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Pipeline welding completed near the crossing.",
            "reporter_name": "Er. Baruah"
        }
    )
    assert dpr_b.status_code == 201
    events_b = dpr_b.json()["events"]
    assert len(events_b) > 0
    event_b_id = events_b[0]["id"]

    match_res_b = await client.post(f"/api/v1/matching/progress-events/{event_b_id}?top_k=5")
    assert match_res_b.status_code == 200
    data_b = match_res_b.json()
    assert len(data_b["candidates"]) >= 2
    # Multiple welding activities appear with NEEDS_REVIEW or arbitration applied
    assert data_b["top_decision"] in ("NEEDS_REVIEW", "AUTO_MATCHED")

    # 4. Test Scenario C — Poor Match (UNMATCHED)
    # "Security gate painting completed."
    dpr_c = await client.post(
        "/api/v1/field-reports/raw-text",
        json={
            "project_id": project_id,
            "raw_text": "Security gate painting completed.",
            "reporter_name": "Er. Baruah"
        }
    )
    assert dpr_c.status_code == 201
    events_c = dpr_c.json()["events"]
    assert len(events_c) > 0
    event_c_id = events_c[0]["id"]

    match_res_c = await client.post(f"/api/v1/matching/progress-events/{event_c_id}?top_k=5")
    assert match_res_c.status_code == 200
    data_c = match_res_c.json()
    top_cand_c = data_c["candidates"][0] if data_c["candidates"] else None
    assert top_cand_c is not None
    assert top_cand_c["confidence_score"] < 0.50
    assert top_cand_c["decision_status"] == "UNMATCHED"
    assert data_c["top_decision"] == "UNMATCHED"

    # 5. Test GET candidates endpoint (persisted cache)
    get_cand_res = await client.get(f"/api/v1/matching/progress-events/{event_a_id}/candidates")
    assert get_cand_res.status_code == 200
    persisted_data = get_cand_res.json()
    assert len(persisted_data["candidates"]) == len(data_a["candidates"])
    assert persisted_data["candidates"][0]["activity_code"] == top_cand_a["activity_code"]

    # 6. Test POST /run endpoint (re-run)
    rerun_res = await client.post(f"/api/v1/matching/progress-events/{event_a_id}/run?top_k=3")
    assert rerun_res.status_code == 200
    rerun_data = rerun_res.json()
    assert len(rerun_data["candidates"]) == 3
