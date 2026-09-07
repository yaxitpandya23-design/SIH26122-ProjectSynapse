import pytest
from pathlib import Path
from httpx import AsyncClient

SAMPLE_CSV_PATH = Path(__file__).resolve().parent.parent.parent / "sample_data" / "schedules" / "oil_india_pipeline_sample.csv"
SAMPLE_DPR_PATH = Path(__file__).resolve().parent.parent.parent / "sample_data" / "field_reports" / "sample_dpr_notes.txt"


@pytest.mark.asyncio
async def test_full_phase1_flow(client: AsyncClient):
    # 1. Create Project
    proj_payload = {
        "name": "Duliajan-Numaligarh 16-inch Crude Pipeline",
        "code": "DNPL-OIL-001",
        "client_name": "Oil India Limited",
        "target_start_date": "2026-10-01",
        "target_finish_date": "2027-01-05"
    }
    resp = await client.post("/api/v1/schedules/projects", json=proj_payload)
    assert resp.status_code == 201, f"Project creation failed: {resp.text}"
    project = resp.json()
    assert project["code"] == "DNPL-OIL-001"
    project_id = project["id"]

    # 2. List Projects
    list_resp = await client.get("/api/v1/schedules/projects")
    assert list_resp.status_code == 200
    projects = list_resp.json()
    assert any(p["id"] == project_id for p in projects)

    # 3. Upload Schedule CSV
    csv_bytes = SAMPLE_CSV_PATH.read_bytes()
    upload_resp = await client.post(
        "/api/v1/schedules/upload-csv",
        data={"project_id": project_id, "version_label": "Baseline Rev 0"},
        files={"file": ("oil_india_pipeline_sample.csv", csv_bytes, "text/csv")},
    )
    assert upload_resp.status_code == 200, f"CSV upload failed: {upload_resp.text}"
    upload_data = upload_resp.json()
    assert upload_data["activities_imported"] == 20
    assert upload_data["dependencies_imported"] > 0
    schedule_version_id = upload_data["schedule_version_id"]

    # 4. Fetch Activities for Project
    acts_resp = await client.get(f"/api/v1/schedules/project/{project_id}/activities")
    assert acts_resp.status_code == 200
    activities = acts_resp.json()
    assert len(activities) == 20
    assert any(a["activity_code"] == "ACT-1030" for a in activities)

    # Filter activities by discipline
    civil_acts_resp = await client.get(f"/api/v1/schedules/project/{project_id}/activities?discipline=CIVIL")
    assert civil_acts_resp.status_code == 200
    civil_acts = civil_acts_resp.json()
    assert all(a["discipline"] == "CIVIL" for a in civil_acts)
    assert len(civil_acts) > 0

    # 5. Ingest Field Report Text
    dpr_text = SAMPLE_DPR_PATH.read_text(encoding="utf-8")
    report_payload = {
        "project_id": project_id,
        "raw_text": dpr_text,
        "reporter_name": "Er. R. Baruah (Execution Lead)",
        "report_date": "2026-10-28"
    }
    field_resp = await client.post("/api/v1/field-reports/raw-text", json=report_payload)
    assert field_resp.status_code == 201, f"Field report ingestion failed: {field_resp.text}"
    field_report = field_resp.json()
    assert field_report["project_id"] == project_id
    assert len(field_report["events"]) >= 5

    # Check extracted events
    events = field_report["events"]
    # Verify welding event extraction
    welding_evt = next((e for e in events if e["discipline"] == "PIPING" and "weld" in e["work_description"].lower()), None)
    assert welding_evt is not None
    assert welding_evt["quantity_reported"] is not None

    # 6. List Field Reports
    reports_resp = await client.get(f"/api/v1/field-reports?project_id={project_id}")
    assert reports_resp.status_code == 200
    reports = reports_resp.json()
    assert len(reports) >= 1

    # 7. List All Extracted Events
    all_events_resp = await client.get(f"/api/v1/field-reports/events/all?project_id={project_id}")
    assert all_events_resp.status_code == 200
    all_events = all_events_resp.json()
    assert len(all_events) >= 5
