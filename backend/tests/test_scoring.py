import pytest
from datetime import date
from app.modules.semantic_matcher.scoring import (
    cosine_similarity,
    score_discipline,
    score_location,
    score_quantity_uom,
    score_temporal,
    calculate_confidence_score,
)
from app.ai.mock_provider import MockProvider


@pytest.mark.asyncio
async def test_embedding_generation_and_cosine_similarity():
    provider = MockProvider()
    vec1 = await provider.get_embedding("Pipeline mainline joint welding")
    vec2 = await provider.get_embedding("Pipeline mainline joint welding")
    vec3 = await provider.get_embedding("Security gate painting")

    assert len(vec1) == 768
    assert len(vec2) == 768
    assert len(vec3) == 768

    # Identical texts must produce identical normalized vectors with cosine similarity == 1.0
    cos_identical = cosine_similarity(vec1, vec2)
    assert abs(cos_identical - 1.0) < 1e-4

    # Different texts must produce lower cosine similarity
    cos_diff = cosine_similarity(vec1, vec3)
    assert 0.0 <= cos_diff < 0.8


def test_discipline_scoring():
    # Exact match
    score, reasons, mismatches = score_discipline("PIPING", "PIPING")
    assert score == 1.0
    assert len(reasons) > 0
    assert len(mismatches) == 0

    # Cross-compatible match (Piping <-> Mechanical)
    score_cross, reasons_cross, _ = score_discipline("PIPING", "MECHANICAL")
    assert score_cross == 0.70

    # Conflict
    score_conflict, _, mismatches_conflict = score_discipline("CIVIL", "ELECTRICAL")
    assert score_conflict == 0.05
    assert len(mismatches_conflict) > 0


def test_location_scoring():
    # Matching chainage within range
    score_in, reasons, mismatches = score_location("Ch 04+200", "Ch 0+000 to Ch 30+000")
    assert score_in == 1.0
    assert len(reasons) > 0

    # Chainage outside range
    score_out, _, mismatches_out = score_location("Ch 45+000", "Ch 0+000 to Ch 30+000")
    assert score_out < 0.30
    assert len(mismatches_out) > 0

    # Station facility match
    score_fac, reasons_fac, _ = score_location("SV-01 bund wall", "SV-01 Ch 15+000")
    assert score_fac == 0.95

    # Neutral fallback when no location
    score_neutral, _, _ = score_location(None, "Ch 0+000 to Ch 30+000")
    assert score_neutral == 0.75


def test_quantity_uom_scoring():
    # Compatible UOM and quantity within bounds
    score_match, reasons, mismatches = score_quantity_uom(
        event_qty=450.0, event_uom="M", planned_qty=1000.0, planned_uom="M"
    )
    assert score_match == 1.0
    assert len(reasons) > 0

    # Incompatible UOM
    score_incomp, _, mismatches_incomp = score_quantity_uom(
        event_qty=450.0, event_uom="JOINTS", planned_qty=1000.0, planned_uom="CUM"
    )
    assert score_incomp == 0.10
    assert len(mismatches_incomp) > 0

    # Neutral when missing UOM
    score_neutral, _, _ = score_quantity_uom(None, None, 1000.0, "M")
    assert score_neutral == 0.70


def test_temporal_scoring():
    # Date inside planned window
    score_in, reasons, _ = score_temporal(
        event_date=date(2026, 11, 1),
        planned_start=date(2026, 10, 20),
        planned_finish=date(2026, 11, 15),
    )
    assert score_in == 1.0

    # Date far outside window (>60 days)
    score_out, _, mismatches_out = score_temporal(
        event_date=date(2027, 3, 1),
        planned_start=date(2026, 10, 20),
        planned_finish=date(2026, 11, 15),
    )
    assert score_out <= 0.35
    assert len(mismatches_out) > 0


@pytest.mark.asyncio
async def test_confidence_formula_and_threshold_decisions():
    provider = MockProvider()
    vec = await provider.get_embedding("Pipeline mainline joint welding")

    # High match -> AUTO_MATCHED (>= 0.85)
    breakdown_high, _, _, status_high = calculate_confidence_score(
        event_embedding=vec,
        activity_embedding=vec,
        event_discipline="PIPING",
        activity_discipline="PIPING",
        event_location="Ch 04+200",
        activity_location="Ch 0+000 to Ch 30+000",
        event_qty=32.0,
        event_uom="JOINTS",
        planned_qty=2400.0,
        planned_uom="JOINTS",
        event_date=date(2026, 11, 1),
        planned_start=date(2026, 10, 27),
        planned_finish=date(2026, 11, 25),
        event_text="Pipeline mainline joint welding",
        activity_text="Pipeline mainline joint welding",
    )
    assert 0.85 <= breakdown_high.final <= 1.0
    assert status_high == "AUTO_MATCHED"
    assert breakdown_high.discipline == 1.0
    assert breakdown_high.location == 1.0

    # Poor match -> UNMATCHED (< 0.50)
    vec_irrelevant = await provider.get_embedding("Security gate painting")
    breakdown_low, _, _, status_low = calculate_confidence_score(
        event_embedding=vec_irrelevant,
        activity_embedding=vec,
        event_discipline="CIVIL",
        activity_discipline="ELECTRICAL",
        event_location="Ch 80+000",
        activity_location="Ch 0+000 to Ch 30+000",
        event_qty=1.0,
        event_uom="NOS",
        planned_qty=2400.0,
        planned_uom="JOINTS",
        event_date=date(2028, 1, 1),
        planned_start=date(2026, 10, 27),
        planned_finish=date(2026, 11, 25),
        event_text="Security gate painting",
        activity_text="Pipeline mainline joint welding",
    )
    assert 0.0 <= breakdown_low.final < 0.50
    assert status_low == "UNMATCHED"


@pytest.mark.asyncio
async def test_semantic_primacy_gating_prevents_false_auto_match():
    """
    Ensure that partial scope descriptions (e.g. Spool erection vs Manifold Piping & Actuator Mounting)
    are strictly capped at <= 0.78 (NEEDS_REVIEW) even if location, discipline, and temporal alignment
    are 100% matched.
    """
    provider = MockProvider()
    vec_partial = await provider.get_embedding("Pipe spool erection")
    vec_activity = await provider.get_embedding("Valve Station 01 Manifold Piping & Actuator Mounting")

    breakdown, reasons, mismatches, status = calculate_confidence_score(
        event_embedding=vec_partial,
        activity_embedding=vec_activity,
        event_discipline="MECHANICAL",
        activity_discipline="MECHANICAL",
        event_location="SV-01",
        activity_location="SV-01 Ch 15+000",
        event_qty=None,
        event_uom=None,
        planned_qty=1.0,
        planned_uom="UNITS",
        event_date=date(2026, 11, 15),
        planned_start=date(2026, 11, 10),
        planned_finish=date(2026, 11, 30),
        event_text="Pipe spool erection Spool erection for Line 24 near Pump House completed today at SV-01.",
        activity_text="ACT-5020 Valve Station 01 Manifold Piping & Actuator Mounting SV-01 Ch 15+000",
    )
    # Even though discipline=1.0, location=0.95, temporal=1.0:
    # Because semantic alignment reflects partial scope (< 0.78), score is strictly capped at <= 0.78!
    assert breakdown.semantic < 0.78
    assert breakdown.final <= 0.78
    assert status == "NEEDS_REVIEW"
    assert any("partial scope" in m.lower() for m in mismatches)

