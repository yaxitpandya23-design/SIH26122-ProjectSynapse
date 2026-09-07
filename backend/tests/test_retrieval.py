import pytest
from app.modules.schedules.models import ScheduleActivity
from app.modules.field_capture.models import ProgressEvent
from app.modules.semantic_matcher.retrieval import (
    compute_bm25_sparse_scores,
    compute_dense_scores,
    reciprocal_rank_fusion,
    hybrid_retrieve_candidates,
)
from app.ai.mock_provider import MockProvider


@pytest.mark.asyncio
async def test_sparse_dense_and_rrf_retrieval():
    provider = MockProvider()

    # Create dummy ScheduleActivity models
    emb_welding = await provider.get_embedding("Pipeline mainline joint welding piping")
    emb_trench = await provider.get_embedding("Trench excavation civil earthworks")
    emb_gate = await provider.get_embedding("Security gate painting boundary")

    act_welding = ScheduleActivity(
        id="act-1",
        activity_code="ACT-2030",
        name="Mainline Pipe Joint Shielded Metal Arc Welding",
        discipline="PIPING",
        wbs_code="1.2.2",
        wbs_name="Piping & Welding",
        location_scope="Ch 0+000 to Ch 30+000",
        planned_quantity=2400.0,
        uom="JOINTS",
        embedding=emb_welding,
    )
    act_trench = ScheduleActivity(
        id="act-2",
        activity_code="ACT-1030",
        name="Trench Excavation for 16-inch Pipeline",
        discipline="CIVIL",
        wbs_code="1.2.1",
        wbs_name="Civil Earthworks",
        location_scope="Ch 0+000 to Ch 30+000",
        planned_quantity=30000.0,
        uom="M",
        embedding=emb_trench,
    )
    act_gate = ScheduleActivity(
        id="act-3",
        activity_code="ACT-9999",
        name="Security Gate Painting",
        discipline="GENERAL",
        wbs_code="9.9.9",
        wbs_name="Miscellaneous",
        location_scope="Main Gate",
        planned_quantity=1.0,
        uom="UNITS",
        embedding=emb_gate,
    )
    activities = [act_welding, act_trench, act_gate]

    # Create ProgressEvent for welding
    event_emb = await provider.get_embedding("Mainline welding team completed 32 butt-weld joints")
    event = ProgressEvent(
        id="evt-1",
        field_report_id="rep-1",
        work_description="Pipeline mainline joint welding",
        discipline="PIPING",
        location_chainage="Ch 04+200",
        quantity_reported=32.0,
        uom="JOINTS",
        status_claim="MILESTONE_COMPLETED",
        raw_text_snippet="Mainline welding team completed 32 butt-weld joints with full root and hot pass near Ch 04+200",
        embedding=event_emb,
    )

    # 1. Sparse BM25
    sparse = compute_bm25_sparse_scores(f"{event.work_description} {event.discipline}", activities)
    assert sparse["act-1"] > sparse["act-3"]

    # 2. Dense Cosine
    dense = compute_dense_scores(event.embedding, activities)
    assert dense["act-1"] > dense["act-3"]

    # 3. RRF Fusion
    rrf = reciprocal_rank_fusion(sparse, dense)
    assert rrf["act-1"] > rrf["act-3"]

    # 4. Hybrid retrieve Top-2
    top_candidates = hybrid_retrieve_candidates(event, activities, top_k=2)
    assert len(top_candidates) == 2
    assert top_candidates[0].activity_code == "ACT-2030"
