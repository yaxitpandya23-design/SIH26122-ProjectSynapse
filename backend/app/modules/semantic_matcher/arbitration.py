import logging
from typing import List, Optional, Tuple
from app.ai.factory import get_llm_provider
from app.ai.base import CandidateArbitrationDTO
from app.modules.field_capture.models import ProgressEvent
from app.modules.semantic_matcher.schemas import MatchCandidateItem

logger = logging.getLogger("synapse.semantic_matcher.arbitration")


async def arbitrate_close_candidates(
    event: ProgressEvent,
    candidates: List[MatchCandidateItem],
    threshold_margin: float = 0.08,
) -> Tuple[bool, Optional[str]]:
    """
    Evaluates whether the top 2 candidates have close scores (< 0.08 margin).
    If triggered, invokes the LLM provider arbitration layer to provide explainable reasoning.
    
    Returns:
    (arbitration_applied: bool, arbitration_reasoning: Optional[str])
    """
    if len(candidates) < 2:
        return False, None

    score_1 = candidates[0].confidence_score
    score_2 = candidates[1].confidence_score

    # Close-candidate arbitration only applies to viable match candidates (score >= 0.50)
    # If the top candidate is already UNMATCHED (< 0.50), no arbitration is warranted.
    if score_1 < 0.50:
        return False, None

    if candidates[0].activity_code == candidates[1].activity_code:
        return False, None

    diff = abs(score_1 - score_2)

    if diff >= threshold_margin:
        return False, None

    logger.info(
        f"Close candidate margin detected ({diff:.4f} < {threshold_margin}). Invoking LLM arbitration..."
    )

    llm_provider = get_llm_provider()

    event_dict = {
        "work_description": event.work_description,
        "discipline": event.discipline,
        "location_chainage": event.location_chainage,
        "quantity_reported": event.quantity_reported,
        "uom": event.uom,
        "raw_text_snippet": event.raw_text_snippet,
    }

    cand1_dict = {
        "activity_id": candidates[0].activity_id,
        "activity_code": candidates[0].activity_code,
        "name": candidates[0].activity_name,
        "discipline": candidates[0].discipline,
        "confidence_score": candidates[0].confidence_score,
    }

    cand2_dict = {
        "activity_id": candidates[1].activity_id,
        "activity_code": candidates[1].activity_code,
        "name": candidates[1].activity_name,
        "discipline": candidates[1].discipline,
        "confidence_score": candidates[1].confidence_score,
    }

    try:
        arbitration_res: CandidateArbitrationDTO = await llm_provider.arbitrate_candidates(
            event_dict=event_dict,
            candidate_1=cand1_dict,
            candidate_2=cand2_dict,
        )

        reasoning = arbitration_res.reasoning

        # Attach LLM reasoning to the top candidates
        candidates[0].llm_reasoning = (
            f"[AI Arbitration]: {reasoning}"
        )
        candidates[1].llm_reasoning = (
            f"[AI Arbitration]: Alternate option evaluated (diff: {diff:.3f})."
        )

        return True, reasoning
    except Exception as e:
        logger.warning(f"LLM arbitration call encountered an exception ({e}).")
        return False, None
