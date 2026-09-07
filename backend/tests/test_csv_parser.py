import pytest
from pathlib import Path
from app.modules.schedules.parsers.csv_parser import parse_schedule_csv

SAMPLE_CSV_PATH = Path(__file__).resolve().parent.parent.parent / "sample_data" / "schedules" / "oil_india_pipeline_sample.csv"


def test_parse_oil_india_schedule_csv():
    assert SAMPLE_CSV_PATH.exists(), f"Sample CSV file not found at {SAMPLE_CSV_PATH}"
    csv_text = SAMPLE_CSV_PATH.read_text(encoding="utf-8")
    
    activities = parse_schedule_csv(csv_text)
    assert len(activities) == 20, f"Expected 20 activities, got {len(activities)}"

    # Verify first activity (Survey)
    act1 = activities[0]
    assert act1.activity_code == "ACT-1010"
    assert "Survey" in act1.name
    assert act1.discipline == "CIVIL"
    assert act1.wbs_code == "1.1.1"
    assert act1.is_critical is True
    assert act1.planned_quantity == 30.0
    assert act1.uom == "KM"

    # Verify activity with predecessors (Trench excavation)
    trench_act = next((a for a in activities if a.activity_code == "ACT-1030"), None)
    assert trench_act is not None
    assert trench_act.planned_quantity == 30000.0
    assert trench_act.uom == "M"
    assert len(trench_act.predecessors_raw) == 1
    assert "ACT-1020:SS:12" in trench_act.predecessors_raw

    # Verify multiple predecessors (Pipe Lowering)
    lowering_act = next((a for a in activities if a.activity_code == "ACT-2060"), None)
    assert lowering_act is not None
    assert len(lowering_act.predecessors_raw) == 2
    assert "ACT-1030" in lowering_act.predecessors_raw
    assert "ACT-2050" in lowering_act.predecessors_raw
