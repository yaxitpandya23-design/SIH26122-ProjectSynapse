import logging
from typing import List, Optional
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_embedding_provider
from app.modules.field_capture.models import ProgressEvent, FieldReport
from app.modules.schedules.models import ScheduleActivity, ScheduleVersion
from app.modules.semantic_matcher.models import ActivityMatchCandidate
from app.modules.semantic_matcher.schemas import (
    MatchCandidateItem,
    MatchRunResponse,
    ScoreBreakdown,
)
from app.modules.semantic_matcher.scoring import calculate_confidence_score
from app.modules.semantic_matcher.retrieval import hybrid_retrieve_candidates
from app.modules.semantic_matcher.arbitration import arbitrate_close_candidates

logger = logging.getLogger("synapse.semantic_matcher.service")


class SemanticMatcherService:

    @staticmethod
    async def run_matching_for_event(
        db: AsyncSession, event_id: str, top_k: int = 5
    ) -> MatchRunResponse:
        """
        Executes the complete Planning-to-Execution matching pipeline for a given ProgressEvent:
        1. Fetch event & project context
        2. Ensure embedding representation exists
        3. Hybrid retrieval (BM25 sparse + dense vector cosine + RRF)
        4. Multi-factor confidence scoring (Semantic 40%, Discipline 20%, Location 20%, Qty 10%, Time 10%)
        5. Explainable ranking & reasoning generation
        6. Close-candidate arbitration (when top 2 delta < 0.15)
        7. Persist match candidates to database
        """
        # 1. Fetch event with parent report
        query = (
            select(ProgressEvent)
            .where(ProgressEvent.id == event_id)
            .options(selectinload(ProgressEvent.field_report))
        )
        res = await db.execute(query)
        event = res.scalars().first()
        if not event:
            raise ValueError(f"ProgressEvent with ID '{event_id}' not found.")

        project_id = event.field_report.project_id if event.field_report else None
        embedding_provider = get_embedding_provider()

        # Ensure event embedding exists
        if not event.embedding:
            semantic_text = f"{event.work_description} | Discipline: {event.discipline} | Loc: {event.location_chainage or ''}"
            event.embedding = await embedding_provider.get_embedding(semantic_text)
            db.add(event)
            await db.flush()

        # 2. Fetch schedule activities for active baseline schedule
        act_query = select(ScheduleActivity)
        if project_id:
            act_query = (
                act_query.join(ScheduleVersion)
                .where(
                    ScheduleVersion.project_id == project_id,
                    ScheduleVersion.is_active_baseline == True,
                )
            )

        act_res = await db.execute(act_query)
        activities = list(act_res.scalars().all())

        # Deduplicate activities by activity_code
        seen_codes = set()
        deduped_activities = []
        for act in activities:
            if act.activity_code not in seen_codes:
                seen_codes.add(act.activity_code)
                deduped_activities.append(act)
        activities = deduped_activities

        # Ensure all activities have embeddings
        for act in activities:
            if not act.embedding:
                act_sem = f"{act.wbs_name or ''} {act.name} | Discipline: {act.discipline} | Scope: {act.location_scope or ''}"
                act.embedding = await embedding_provider.get_embedding(act_sem)
                db.add(act)
        await db.flush()

        # 3. Hybrid Retrieval: candidate pool
        candidate_pool = hybrid_retrieve_candidates(event, activities, top_k=max(10, top_k * 2))

        # 4. Multi-factor Confidence Scoring & Explainability
        scored_candidates: List[MatchCandidateItem] = []
        event_full_text = f"{event.work_description} {event.raw_text_snippet or ''}"

        for act in candidate_pool:
            act_full_text = f"{act.activity_code} {act.name} {act.wbs_name or ''} {act.location_scope or ''}"
            breakdown, reasons, mismatches, dec_status = calculate_confidence_score(
                event_embedding=event.embedding,
                activity_embedding=act.embedding,
                event_discipline=event.discipline,
                activity_discipline=act.discipline,
                event_location=event.location_chainage,
                activity_location=act.location_scope,
                event_qty=event.quantity_reported,
                event_uom=event.uom,
                planned_qty=act.planned_quantity,
                planned_uom=act.uom,
                event_date=event.event_date,
                planned_start=act.planned_start,
                planned_finish=act.planned_finish,
                event_text=event_full_text,
                activity_text=act_full_text,
            )

            scored_candidates.append(
                MatchCandidateItem(
                    activity_id=act.id,
                    activity_code=act.activity_code,
                    activity_name=act.name,
                    discipline=act.discipline,
                    wbs_code=act.wbs_code,
                    wbs_name=act.wbs_name,
                    location_scope=act.location_scope,
                    planned_quantity=act.planned_quantity,
                    actual_quantity=act.actual_quantity,
                    uom=act.uom,
                    confidence_score=breakdown.final,
                    score_breakdown=breakdown,
                    ranking=0,
                    matching_reasons=reasons,
                    mismatch_reasons=mismatches,
                    decision_status=dec_status,
                    llm_reasoning=None,
                )
            )

        # Sort candidates descending by confidence score
        scored_candidates.sort(key=lambda c: c.confidence_score, reverse=True)
        top_candidates = scored_candidates[:top_k]

        # Assign 1-indexed rankings
        for idx, cand in enumerate(top_candidates):
            cand.ranking = idx + 1

        # 5. Close-Candidate Arbitration (if margin < 0.08)
        arbitration_applied, arbitration_reasoning = await arbitrate_close_candidates(
            event=event, candidates=top_candidates, threshold_margin=0.08
        )

        # 6. Determine Top Decision
        top_decision = "UNMATCHED"
        if top_candidates:
            best = top_candidates[0]
            if arbitration_applied:
                # Ambiguous close cases require human review
                top_decision = "NEEDS_REVIEW"
                best.decision_status = "NEEDS_REVIEW"
            else:
                top_decision = best.decision_status

        # 7. Persist Candidates to Database
        # Clean up existing candidates for this event first to prevent duplication
        await db.execute(
            delete(ActivityMatchCandidate).where(
                ActivityMatchCandidate.progress_event_id == event.id
            )
        )

        for cand in top_candidates:
            candidate_record = ActivityMatchCandidate(
                progress_event_id=event.id,
                activity_id=cand.activity_id,
                confidence_score=cand.confidence_score,
                score_breakdown=cand.score_breakdown.model_dump(),
                status=cand.decision_status,
                llm_reasoning=cand.llm_reasoning,
            )
            db.add(candidate_record)
            await db.flush()
            cand.candidate_id = candidate_record.id

        await db.commit()

        return MatchRunResponse(
            event_id=event.id,
            event_work_description=event.work_description,
            event_discipline=event.discipline,
            event_location=event.location_chainage,
            event_quantity=event.quantity_reported,
            event_uom=event.uom,
            top_decision=top_decision,
            arbitration_applied=arbitration_applied,
            arbitration_reasoning=arbitration_reasoning,
            candidates=top_candidates,
        )

    @staticmethod
    async def get_candidates_for_event(
        db: AsyncSession, event_id: str
    ) -> MatchRunResponse:
        """Fetch previously computed candidates or run matching if none exist."""
        query = (
            select(ActivityMatchCandidate)
            .where(ActivityMatchCandidate.progress_event_id == event_id)
            .options(selectinload(ActivityMatchCandidate.activity))
            .order_by(ActivityMatchCandidate.confidence_score.desc())
        )
        res = await db.execute(query)
        persisted = list(res.scalars().all())

        if not persisted:
            # If no candidates yet stored, execute matching
            return await SemanticMatcherService.run_matching_for_event(db, event_id)

        # Fetch event
        ev_query = select(ProgressEvent).where(ProgressEvent.id == event_id)
        ev_res = await db.execute(ev_query)
        event = ev_res.scalars().first()
        if not event:
            raise ValueError(f"ProgressEvent '{event_id}' not found.")

        candidates_items: List[MatchCandidateItem] = []
        arbitration_applied = False
        arbitration_reasoning = None

        for idx, rec in enumerate(persisted):
            act = rec.activity
            breakdown_dict = rec.score_breakdown or {}
            breakdown = ScoreBreakdown(
                semantic=breakdown_dict.get("semantic", 0.0),
                discipline=breakdown_dict.get("discipline", 0.0),
                location=breakdown_dict.get("location", 0.0),
                quantity=breakdown_dict.get("quantity", 0.0),
                temporal=breakdown_dict.get("temporal", 0.0),
                final=rec.confidence_score,
            )

            if rec.llm_reasoning and "[AI Arbitration]" in rec.llm_reasoning:
                arbitration_applied = True
                arbitration_reasoning = rec.llm_reasoning

            candidates_items.append(
                MatchCandidateItem(
                    candidate_id=rec.id,
                    activity_id=act.id if act else "",
                    activity_code=act.activity_code if act else "",
                    activity_name=act.name if act else "Unknown Activity",
                    discipline=act.discipline if act else "GENERAL",
                    wbs_code=act.wbs_code if act else "",
                    wbs_name=act.wbs_name if act else None,
                    location_scope=act.location_scope if act else None,
                    planned_quantity=act.planned_quantity if act else 0.0,
                    actual_quantity=act.actual_quantity if act else 0.0,
                    uom=act.uom if act else None,
                    confidence_score=rec.confidence_score,
                    score_breakdown=breakdown,
                    ranking=idx + 1,
                    matching_reasons=["Persisted match record"],
                    mismatch_reasons=[],
                    decision_status=rec.status,
                    llm_reasoning=rec.llm_reasoning,
                )
            )

        top_decision = candidates_items[0].decision_status if candidates_items else "UNMATCHED"

        return MatchRunResponse(
            event_id=event.id,
            event_work_description=event.work_description,
            event_discipline=event.discipline,
            event_location=event.location_chainage,
            event_quantity=event.quantity_reported,
            event_uom=event.uom,
            top_decision=top_decision,
            arbitration_applied=arbitration_applied,
            arbitration_reasoning=arbitration_reasoning,
            candidates=candidates_items,
        )
