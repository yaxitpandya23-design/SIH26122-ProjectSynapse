import logging
from datetime import datetime, date, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_, delete

from app.modules.schedules.models import Project, ScheduleVersion, ScheduleActivity
from app.modules.field_capture.models import FieldReport, ProgressEvent
from app.modules.semantic_matcher.models import ActivityMatchCandidate
from app.modules.dependency_validator.models import DependencyViolation
from app.modules.dependency_validator.schemas import DependencyViolationDTO
from app.modules.dependency_validator.service import DependencyValidatorService
from app.modules.semantic_matcher.service import SemanticMatcherService
from app.modules.review_inbox.models import ReviewAudit
from app.modules.review_inbox.schemas import (
    ReviewInboxItemDTO,
    ReviewCandidateDetailDTO,
    ReviewMutationResponseDTO,
    ReviewAuditLogDTO,
    DashboardStatsDTO,
    ReviewActionEditDTO,
)

logger = logging.getLogger("synapse.review_inbox.service")


class QuantitySemantics(str, Enum):
    INCREMENTAL = "INCREMENTAL"
    CUMULATIVE = "CUMULATIVE"
    UNKNOWN = "UNKNOWN"


def detect_quantity_semantics(event: ProgressEvent, raw_text: Optional[str] = None) -> QuantitySemantics:
    """
    Deterministic rule-based classification of quantity reporting semantics.
    Strictly non-generative to prevent AI hallucination of schedule progress.
    """
    search_texts = []
    if event.work_description:
        search_texts.append(event.work_description.lower())
    if event.raw_text_snippet:
        search_texts.append(event.raw_text_snippet.lower())
    if raw_text:
        search_texts.append(raw_text.lower())

    combined_text = " ".join(search_texts)

    cumulative_markers = [
        "total to date",
        "cumulative",
        "total achieved",
        "to date",
        "overall",
        "total of",
        "reaches",
        "reached",
    ]
    for marker in cumulative_markers:
        if marker in combined_text:
            return QuantitySemantics.CUMULATIVE

    incremental_markers = [
        "additional",
        "more",
        "installed another",
        "completed today",
        "executed today",
        "poured today",
        "today's progress",
        "progress today",
        "further",
        "added",
        "installed today",
        "laid today",
        "welded today",
        "strung today",
        "excavated today",
        "backfilled today",
    ]
    for marker in incremental_markers:
        if marker in combined_text:
            return QuantitySemantics.INCREMENTAL

    return QuantitySemantics.UNKNOWN


async def _get_project_id_for_event(db: AsyncSession, progress_event_id: str) -> Optional[str]:
    """Helper to reliably retrieve project_id for audit logging across all review actions."""
    res = await db.execute(
        select(FieldReport.project_id)
        .join(ProgressEvent, ProgressEvent.field_report_id == FieldReport.id)
        .where(ProgressEvent.id == progress_event_id)
    )
    return res.scalar_one_or_none()


class ScheduleUpdateService:
    """
    CRITICAL ARCHITECTURAL SAFETY GUARANTEE:
    This service is the SOLE path through which ScheduleActivity actual fields may be mutated.
    AI services, matchers, extractors, and validators NEVER write directly to schedule actuals.
    
    Allowed fields ONLY:
    - actual_quantity
    - actual_start
    - actual_finish
    - physical_percent_complete
    
    Planned baseline fields are strictly immutable.
    ReviewAudit provides an immutable, append-only log at the application layer with transactional atomicity.
    """

    @staticmethod
    async def apply_approved_candidate(
        db: AsyncSession,
        candidate_id: str,
        reviewer_user: str = "Site Planning Engineer",
        remarks: Optional[str] = None,
        is_override: bool = False,
        override_reason: Optional[str] = None,
    ) -> ReviewMutationResponseDTO:
        """
        Atomically applies an approved or overridden candidate's progress to ScheduleActivity actual fields.
        Guarantees idempotency, row-level locking concurrency protection, state machine enforcement,
        optimistic concurrency control via actuals_version, and strict non-fabrication quantity semantics.
        """
        try:
            # 1. Fetch Match Candidate with Row-Level Lock
            cand_res = await db.execute(
                select(ActivityMatchCandidate)
                .where(ActivityMatchCandidate.id == candidate_id)
                .with_for_update()
            )
            candidate = cand_res.scalar_one_or_none()
            if not candidate:
                raise ValueError(f"Match candidate '{candidate_id}' not found.")

            # 2. Fetch Associated Activity with Row-Level Lock
            act_res = await db.execute(
                select(ScheduleActivity)
                .where(ScheduleActivity.id == candidate.activity_id)
                .with_for_update()
            )
            activity = act_res.scalar_one_or_none()
            if not activity:
                raise ValueError(f"ScheduleActivity '{candidate.activity_id}' not found.")

            # 3. Fetch Associated Progress Event & Project
            event_res = await db.execute(
                select(ProgressEvent).where(ProgressEvent.id == candidate.progress_event_id)
            )
            event = event_res.scalar_one_or_none()
            if not event:
                raise ValueError(f"ProgressEvent '{candidate.progress_event_id}' not found.")

            report_res = await db.execute(
                select(FieldReport).where(FieldReport.id == event.field_report_id)
            )
            report = report_res.scalar_one_or_none()
            project_id = report.project_id if report else await _get_project_id_for_event(db, event.id)

            # 4. IDEMPOTENCY CHECK
            if candidate.status == "APPLIED":
                logger.info(f"Idempotency triggered: Candidate '{candidate_id}' was already applied.")
                return ReviewMutationResponseDTO(
                    status="ALREADY_APPLIED",
                    message="Candidate has already been approved and applied. No duplicate actuals were added.",
                    candidate_id=candidate.id,
                    activity_code=activity.activity_code,
                    action="NOOP",
                    previous_values={
                        "actual_quantity": float(activity.actual_quantity or 0.0),
                        "actual_start": str(activity.actual_start) if activity.actual_start else None,
                        "actual_finish": str(activity.actual_finish) if activity.actual_finish else None,
                        "physical_percent_complete": float(activity.physical_percent_complete or 0.0),
                    },
                    new_values={
                        "actual_quantity": float(activity.actual_quantity or 0.0),
                        "actual_start": str(activity.actual_start) if activity.actual_start else None,
                        "actual_finish": str(activity.actual_finish) if activity.actual_finish else None,
                        "physical_percent_complete": float(activity.physical_percent_complete or 0.0),
                    },
                )

            # 5. STATE MACHINE GOVERNANCE CHECKS
            if candidate.status == "REJECTED":
                raise ValueError("Rejected candidate cannot be applied to the schedule.")

            if candidate.status == "UNMATCHED":
                raise ValueError("Unmatched candidate cannot be applied to the schedule.")

            if candidate.status == "STALE_REVIEW":
                raise ValueError("Candidate is marked as STALE_REVIEW. Re-validation required before approval.")

            if candidate.status not in ("AUTO_MATCHED", "NEEDS_REVIEW", "BLOCKED_BY_DEPENDENCY"):
                raise ValueError(f"Candidate in state '{candidate.status}' cannot be applied to the schedule.")

            # 6. HARD VIOLATION & DEPENDENCY BLOCKER GUARD
            viols_res = await db.execute(
                select(DependencyViolation).where(
                    DependencyViolation.match_candidate_id == candidate.id,
                    DependencyViolation.severity == "HARD_VIOLATION",
                )
            )
            hard_violations = list(viols_res.scalars().all())

            if (candidate.status == "BLOCKED_BY_DEPENDENCY" or len(hard_violations) > 0) and not is_override:
                raise ValueError(
                    f"Candidate [{activity.activity_code}] has {len(hard_violations)} unresolved schedule/dependency hard violation(s). "
                    f"Standard approval is prohibited. Explicit override with justification is mandatory."
                )

            if is_override:
                if not override_reason or len(override_reason.strip()) < 5:
                    raise ValueError("An explicit override reason of at least 5 characters is mandatory when overriding schedule blockers.")

            # 7. OPTIMISTIC CONCURRENCY CONTROL & STALE DATA PROTECTION
            activity_version = getattr(activity, "actuals_version", 1) or 1
            validated_version = getattr(candidate, "validated_activity_version", 1) or 1

            if validated_version != activity_version:
                candidate.status = "STALE_REVIEW"
                await db.commit()
                return ReviewMutationResponseDTO(
                    status="STALE_REVIEW",
                    message=f"ScheduleActivity [{activity.activity_code}] actuals were updated (activity version {activity_version} != validated {validated_version}). Marked candidate as STALE_REVIEW. Re-validation required.",
                    candidate_id=candidate.id,
                    activity_code=activity.activity_code,
                    action="STALE_CHECK",
                )

            if activity.actual_finish is not None and event.status_claim not in ("COMPLETED", "MILESTONE_COMPLETED"):
                candidate.status = "STALE_REVIEW"
                await db.commit()
                return ReviewMutationResponseDTO(
                    status="STALE_REVIEW",
                    message=f"ScheduleActivity [{activity.activity_code}] already finished independently. Marked candidate as STALE_REVIEW. Re-validation required.",
                    candidate_id=candidate.id,
                    activity_code=activity.activity_code,
                    action="STALE_CHECK",
                )

            # 8. SNAPSHOT PREVIOUS ACTUAL VALUES
            previous_values = {
                "actual_quantity": float(activity.actual_quantity or 0.0),
                "actual_start": str(activity.actual_start) if activity.actual_start else None,
                "actual_finish": str(activity.actual_finish) if activity.actual_finish else None,
                "physical_percent_complete": float(activity.physical_percent_complete or 0.0),
            }

            # 9. PROGRESS APPLICATION LOGIC (Strict Non-Fabrication & Quantity Semantics)
            event_effective_date = event.event_date or (report.report_date if report else None) or date.today()
            curr_qty = float(activity.actual_quantity or 0.0)
            reported_qty = float(event.quantity_reported) if (event.quantity_reported is not None and event.quantity_reported > 0) else None
            semantics = detect_quantity_semantics(event, report.raw_source_text if report else None)

            if reported_qty is None:
                # Strictly preserve existing actual_quantity without fabricating planned_quantity or 1.0
                act_qty = curr_qty
            else:
                if semantics == QuantitySemantics.CUMULATIVE:
                    act_qty = max(curr_qty, reported_qty)
                elif semantics == QuantitySemantics.INCREMENTAL:
                    act_qty = curr_qty + reported_qty
                else:  # UNKNOWN
                    # Deterministic rule: initialize if curr_qty == 0.0; otherwise preserve existing actuals
                    if curr_qty == 0.0:
                        act_qty = reported_qty
                    else:
                        act_qty = curr_qty

            if event.status_claim in ("COMPLETED", "MILESTONE_COMPLETED"):
                act_start = activity.actual_start or event_effective_date
                act_finish = event_effective_date
                act_percent = 100.0
            elif event.status_claim == "IN_PROGRESS":
                act_start = activity.actual_start or event_effective_date
                act_finish = None
                if activity.planned_quantity > 0 and act_qty > 0:
                    act_percent = min(99.0, round((act_qty / activity.planned_quantity) * 100.0, 1))
                else:
                    act_percent = max(float(activity.physical_percent_complete or 0.0), 50.0)
            else:  # STARTED
                act_start = activity.actual_start or event_effective_date
                act_finish = None
                act_percent = max(float(activity.physical_percent_complete or 0.0), 5.0)

            # 10. APPLY ONLY TO ALLOWED ACTUAL FIELDS AND BUMP OCC VERSION
            activity.actual_quantity = act_qty
            activity.actual_start = act_start
            activity.actual_finish = act_finish
            activity.physical_percent_complete = act_percent
            activity.actuals_version = activity_version + 1

            # 11. UPDATE CANDIDATE STATUS
            candidate.status = "APPLIED"

            # 12. CREATE AUDIT RECORD (Application-level Append-Only Audit Trail)
            new_values = {
                "actual_quantity": act_qty,
                "actual_start": str(act_start) if act_start else None,
                "actual_finish": str(act_finish) if act_finish else None,
                "physical_percent_complete": act_percent,
            }

            audit_record = ReviewAudit(
                project_id=project_id,
                match_candidate_id=candidate.id,
                progress_event_id=event.id,
                activity_id=activity.id,
                activity_code=activity.activity_code,
                action="OVERRIDDEN" if is_override else "APPROVED",
                decision="OVERRIDE" if is_override else "APPROVE",
                reviewer_user=reviewer_user,
                review_timestamp=datetime.now(timezone.utc),
                remarks=remarks or (f"Override applied: {override_reason}" if is_override else "Progress applied to schedule actuals upon engineer approval."),
                is_override=is_override,
                override_reason=override_reason,
                previous_values=previous_values,
                new_values=new_values,
            )
            db.add(audit_record)

            await db.commit()

            logger.info(
                f"Schedule actuals mutated for [{activity.activity_code}] by '{reviewer_user}' (Action: {'OVERRIDDEN' if is_override else 'APPROVED'}, Version: {activity.actuals_version})."
            )

            return ReviewMutationResponseDTO(
                status="APPLIED",
                message=f"Schedule actuals successfully updated for [{activity.activity_code}].",
                candidate_id=candidate.id,
                activity_code=activity.activity_code,
                action="OVERRIDDEN" if is_override else "APPROVED",
                previous_values=previous_values,
                new_values=new_values,
                audit_id=audit_record.id,
            )
        except Exception as e:
            await db.rollback()
            logger.error(f"Transaction failed in apply_approved_candidate: {e}")
            raise


class ReviewInboxService:
    """
    Human-in-the-Loop review queue management, candidate inspection, and audit logging.
    Delegates schedule mutations exclusively to ScheduleUpdateService.
    """

    @staticmethod
    async def get_inbox_items(
        db: AsyncSession,
        project_id: Optional[str] = None,
        status_filter: Optional[str] = None,
        severity_filter: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ReviewInboxItemDTO]:
        """Retrieves candidates requiring planner review or eligible for approval."""
        query = (
            select(ActivityMatchCandidate, ProgressEvent, FieldReport, ScheduleActivity)
            .join(ProgressEvent, ActivityMatchCandidate.progress_event_id == ProgressEvent.id)
            .join(FieldReport, ProgressEvent.field_report_id == FieldReport.id)
            .join(ScheduleActivity, ActivityMatchCandidate.activity_id == ScheduleActivity.id)
        )

        if project_id:
            query = query.where(FieldReport.project_id == project_id)

        if status_filter and status_filter != "ALL":
            query = query.where(ActivityMatchCandidate.status == status_filter)

        query = query.order_by(desc(ActivityMatchCandidate.confidence_score), desc(ActivityMatchCandidate.created_at))
        query = query.limit(limit).offset(offset)

        res = await db.execute(query)
        rows = res.all()

        inbox_items: List[ReviewInboxItemDTO] = []
        for cand, event, report, act in rows:
            # Fetch violations for this candidate
            viols_res = await db.execute(
                select(DependencyViolation).where(DependencyViolation.match_candidate_id == cand.id)
            )
            violations = list(viols_res.scalars().all())

            has_hard = any(v.severity == "HARD_VIOLATION" for v in violations)
            has_soft = any(v.severity == "SOFT_WARNING" for v in violations)
            blocker_reasons = [v.description for v in violations if v.severity == "HARD_VIOLATION"]

            # Compute discrete check indicators
            checks = {
                "predecessor": "FAIL" if any(v.violation_type == "PREDECESSOR_INCOMPLETE" for v in violations) else "PASS",
                "sequence": "FAIL" if any(v.violation_type == "OUT_OF_SEQUENCE" for v in violations) else "PASS",
                "quantity": "FAIL" if any(v.violation_type == "QUANTITY_OVERRUN" and v.severity == "HARD_VIOLATION" for v in violations) else ("WARNING" if any(v.violation_type == "QUANTITY_OVERRUN" for v in violations) else "PASS"),
                "critical_path": "WARNING" if any(v.violation_type == "CRITICAL_PATH_RISK" for v in violations) else "PASS",
            }

            can_appr = (cand.status in ("AUTO_MATCHED", "NEEDS_REVIEW")) and not has_hard and cand.status != "APPLIED" and cand.status != "REJECTED"
            can_over = has_hard and cand.status != "APPLIED" and cand.status != "REJECTED"

            inbox_items.append(
                ReviewInboxItemDTO(
                    candidate_id=cand.id,
                    progress_event_id=event.id,
                    project_id=report.project_id,
                    report_date=str(report.report_date) if report.report_date else None,
                    reporter_name=report.reporter_name,
                    raw_text_snippet=event.raw_text_snippet,
                    work_description=event.work_description,
                    discipline=event.discipline,
                    location_chainage=event.location_chainage,
                    quantity_reported=event.quantity_reported,
                    uom=event.uom,
                    status_claim=event.status_claim,
                    event_date=str(event.event_date) if event.event_date else None,
                    activity_id=act.id,
                    activity_code=act.activity_code,
                    activity_name=act.name,
                    activity_discipline=act.discipline,
                    planned_quantity=float(act.planned_quantity or 0.0),
                    actual_quantity=float(act.actual_quantity or 0.0),
                    activity_uom=act.uom,
                    confidence_score=cand.confidence_score,
                    score_breakdown=cand.score_breakdown or {},
                    status=cand.status,
                    has_hard_violations=has_hard,
                    has_soft_warnings=has_soft,
                    violations_count=len(violations),
                    is_critical=act.is_critical,
                    total_float_days=act.total_float_days,
                    validation_checks=checks,
                    blocker_reasons=blocker_reasons,
                    can_approve=can_appr,
                    can_override=can_over,
                    is_applied=cand.status == "APPLIED",
                )
            )

        if severity_filter and severity_filter != "ALL":
            if severity_filter == "HARD_VIOLATION":
                inbox_items = [item for item in inbox_items if item.has_hard_violations]
            elif severity_filter == "SOFT_WARNING":
                inbox_items = [item for item in inbox_items if item.has_soft_warnings and not item.has_hard_violations]

        return inbox_items

    @staticmethod
    async def get_candidate_detail(
        db: AsyncSession, candidate_id: str
    ) -> ReviewCandidateDetailDTO:
        """Retrieves complete 360-degree context for candidate inspection."""
        query = (
            select(ActivityMatchCandidate, ProgressEvent, FieldReport, ScheduleActivity)
            .join(ProgressEvent, ActivityMatchCandidate.progress_event_id == ProgressEvent.id)
            .join(FieldReport, ProgressEvent.field_report_id == FieldReport.id)
            .join(ScheduleActivity, ActivityMatchCandidate.activity_id == ScheduleActivity.id)
            .where(ActivityMatchCandidate.id == candidate_id)
        )
        res = await db.execute(query)
        row = res.first()
        if not row:
            raise ValueError(f"Match candidate '{candidate_id}' not found.")

        cand, event, report, act = row

        viols_res = await db.execute(
            select(DependencyViolation).where(DependencyViolation.match_candidate_id == cand.id)
        )
        violations = list(viols_res.scalars().all())

        has_hard = any(v.severity == "HARD_VIOLATION" for v in violations)
        has_soft = any(v.severity == "SOFT_WARNING" for v in violations)
        blocker_reasons = [v.description for v in violations if v.severity == "HARD_VIOLATION"]

        checks = {
            "predecessor": "FAIL" if any(v.violation_type == "PREDECESSOR_INCOMPLETE" for v in violations) else "PASS",
            "sequence": "FAIL" if any(v.violation_type == "OUT_OF_SEQUENCE" for v in violations) else "PASS",
            "quantity": "FAIL" if any(v.violation_type == "QUANTITY_OVERRUN" and v.severity == "HARD_VIOLATION" for v in violations) else ("WARNING" if any(v.violation_type == "QUANTITY_OVERRUN" for v in violations) else "PASS"),
            "critical_path": "WARNING" if any(v.violation_type == "CRITICAL_PATH_RISK" for v in violations) else "PASS",
        }

        can_appr = (cand.status in ("AUTO_MATCHED", "NEEDS_REVIEW")) and not has_hard and cand.status != "APPLIED" and cand.status != "REJECTED"
        can_over = has_hard and cand.status != "APPLIED" and cand.status != "REJECTED"

        return ReviewCandidateDetailDTO(
            candidate_id=cand.id,
            progress_event_id=event.id,
            project_id=report.project_id,
            report_date=str(report.report_date) if report.report_date else None,
            reporter_name=report.reporter_name,
            raw_text_snippet=event.raw_text_snippet,
            raw_source_text=report.raw_source_text,
            work_description=event.work_description,
            discipline=event.discipline,
            location_chainage=event.location_chainage,
            quantity_reported=event.quantity_reported,
            uom=event.uom,
            status_claim=event.status_claim,
            event_date=str(event.event_date) if event.event_date else None,
            activity_id=act.id,
            activity_code=act.activity_code,
            activity_name=act.name,
            activity_discipline=act.discipline,
            planned_quantity=float(act.planned_quantity or 0.0),
            actual_quantity=float(act.actual_quantity or 0.0),
            activity_uom=act.uom,
            confidence_score=cand.confidence_score,
            score_breakdown=cand.score_breakdown or {},
            status=cand.status,
            has_hard_violations=has_hard,
            has_soft_warnings=has_soft,
            violations_count=len(violations),
            is_critical=act.is_critical,
            total_float_days=act.total_float_days,
            validation_checks=checks,
            blocker_reasons=blocker_reasons,
            can_approve=can_appr,
            can_override=can_over,
            is_applied=cand.status == "APPLIED",
            is_stale=cand.status == "STALE_REVIEW",
            llm_reasoning=cand.llm_reasoning,
            violations=[DependencyViolationDTO.model_validate(v) for v in violations],
            previous_actuals={
                "actual_quantity": float(act.actual_quantity or 0.0),
                "actual_start": str(act.actual_start) if act.actual_start else None,
                "actual_finish": str(act.actual_finish) if act.actual_finish else None,
                "physical_percent_complete": float(act.physical_percent_complete or 0.0),
            },
        )

    @staticmethod
    async def reject_candidate(
        db: AsyncSession, candidate_id: str, reason: str, reviewer_user: str = "Site Planning Engineer"
    ) -> ReviewMutationResponseDTO:
        """Rejects a candidate. Zero schedule actuals modified."""
        try:
            cand_res = await db.execute(
                select(ActivityMatchCandidate).where(ActivityMatchCandidate.id == candidate_id)
            )
            candidate = cand_res.scalar_one_or_none()
            if not candidate:
                raise ValueError(f"Match candidate '{candidate_id}' not found.")

            act_res = await db.execute(
                select(ScheduleActivity).where(ScheduleActivity.id == candidate.activity_id)
            )
            activity = act_res.scalar_one_or_none()

            project_id = await _get_project_id_for_event(db, candidate.progress_event_id)

            candidate.status = "REJECTED"

            audit = ReviewAudit(
                project_id=project_id,
                match_candidate_id=candidate.id,
                progress_event_id=candidate.progress_event_id,
                activity_id=candidate.activity_id,
                activity_code=activity.activity_code if activity else None,
                action="REJECTED",
                decision="REJECT",
                reviewer_user=reviewer_user,
                review_timestamp=datetime.now(timezone.utc),
                remarks=reason,
                is_override=False,
                previous_values={},
                new_values={},
            )
            db.add(audit)
            await db.commit()

            return ReviewMutationResponseDTO(
                status="REJECTED",
                message=f"Candidate [{activity.activity_code if activity else candidate_id}] successfully rejected.",
                candidate_id=candidate.id,
                activity_code=activity.activity_code if activity else "UNKNOWN",
                action="REJECTED",
                audit_id=audit.id,
            )
        except Exception as e:
            await db.rollback()
            logger.error(f"Transaction failed during reject_candidate: {e}")
            raise

    @staticmethod
    async def reassign_candidate(
        db: AsyncSession,
        candidate_id: str,
        target_activity_id: str,
        reason: Optional[str] = None,
        reviewer_user: str = "Site Planning Engineer",
    ) -> ReviewMutationResponseDTO:
        """
        Reassigns candidate to another activity in the schedule.
        NEVER mutates schedule actuals. Triggers fresh deterministic validation.
        """
        try:
            cand_res = await db.execute(
                select(ActivityMatchCandidate).where(ActivityMatchCandidate.id == candidate_id)
            )
            candidate = cand_res.scalar_one_or_none()
            if not candidate:
                raise ValueError(f"Match candidate '{candidate_id}' not found.")

            target_res = await db.execute(
                select(ScheduleActivity).where(ScheduleActivity.id == target_activity_id)
            )
            target_activity = target_res.scalar_one_or_none()
            if not target_activity:
                raise ValueError(f"Target ScheduleActivity '{target_activity_id}' not found.")

            project_id = await _get_project_id_for_event(db, candidate.progress_event_id)
            old_act_id = candidate.activity_id
            candidate.activity_id = target_activity.id

            # Fresh deterministic validation against the new activity
            val_res = await DependencyValidatorService.validate_candidate(db, candidate.id)

            audit = ReviewAudit(
                project_id=project_id,
                match_candidate_id=candidate.id,
                progress_event_id=candidate.progress_event_id,
                activity_id=target_activity.id,
                activity_code=target_activity.activity_code,
                action="REASSIGNED",
                decision="REASSIGN",
                reviewer_user=reviewer_user,
                review_timestamp=datetime.now(timezone.utc),
                remarks=reason or f"Reassigned activity from {old_act_id} to {target_activity.activity_code}",
                is_override=False,
                previous_values={"activity_id": old_act_id},
                new_values={"activity_id": target_activity.id, "final_decision": val_res.final_decision},
            )
            db.add(audit)
            await db.commit()

            return ReviewMutationResponseDTO(
                status="REASSIGNED",
                message=f"Candidate successfully reassigned to [{target_activity.activity_code}] and re-validated (Result: {val_res.final_decision}).",
                candidate_id=candidate.id,
                activity_code=target_activity.activity_code,
                action="REASSIGNED",
                audit_id=audit.id,
            )
        except Exception as e:
            await db.rollback()
            logger.error(f"Transaction failed during reassign_candidate: {e}")
            raise

    @staticmethod
    async def edit_progress_event(
        db: AsyncSession,
        candidate_id: str,
        payload: ReviewActionEditDTO,
        reviewer_user: str = "Site Planning Engineer",
    ) -> ReviewMutationResponseDTO:
        """
        Edits reported ProgressEvent values without mutating baseline schedule.
        - If match-relevant fields (work_description) change, invalidates previous match decision (NEEDS_REMATCH).
        - If only progress parameters (quantity, date, status) change, triggers fresh Phase 3 validation.
        """
        try:
            cand_res = await db.execute(
                select(ActivityMatchCandidate).where(ActivityMatchCandidate.id == candidate_id)
            )
            candidate = cand_res.scalar_one_or_none()
            if not candidate:
                raise ValueError(f"Match candidate '{candidate_id}' not found.")

            event_res = await db.execute(
                select(ProgressEvent).where(ProgressEvent.id == candidate.progress_event_id)
            )
            event = event_res.scalar_one_or_none()
            if not event:
                raise ValueError(f"ProgressEvent '{candidate.progress_event_id}' not found.")

            act_res = await db.execute(
                select(ScheduleActivity).where(ScheduleActivity.id == candidate.activity_id)
            )
            activity = act_res.scalar_one_or_none()
            act_code = activity.activity_code if activity else "UNKNOWN"

            project_id = await _get_project_id_for_event(db, event.id)

            # Check if match-relevant description changed
            work_desc_changed = (
                payload.work_description is not None
                and payload.work_description.strip() != ""
                and payload.work_description.strip() != (event.work_description or "").strip()
            )

            # Update event fields
            if payload.quantity_reported is not None:
                event.quantity_reported = payload.quantity_reported
            if payload.uom is not None:
                event.uom = payload.uom
            if payload.event_date is not None:
                event.event_date = date.fromisoformat(payload.event_date)
            if payload.status_claim is not None:
                event.status_claim = payload.status_claim
            if payload.work_description is not None:
                event.work_description = payload.work_description

            await db.flush()

            if work_desc_changed:
                # Invalidate previous match decision and violations
                await db.execute(
                    delete(DependencyViolation).where(
                        DependencyViolation.match_candidate_id == candidate.id
                    )
                )
                candidate.status = "NEEDS_REMATCH"
                candidate.confidence_score = 0.0
                candidate.score_breakdown = {}
                candidate.llm_reasoning = "ProgressEvent work description modified. Rematching required before validation or approval."
                event.embedding = None

                audit = ReviewAudit(
                    project_id=project_id,
                    match_candidate_id=candidate.id,
                    progress_event_id=event.id,
                    activity_id=candidate.activity_id,
                    activity_code=act_code,
                    action="EDITED",
                    decision="EDIT",
                    reviewer_user=reviewer_user,
                    review_timestamp=datetime.now(timezone.utc),
                    remarks=payload.reason or "ProgressEvent work description edited. Match invalidated (NEEDS_REMATCH).",
                    is_override=False,
                    previous_values={},
                    new_values={
                        "work_description": event.work_description,
                        "status": "NEEDS_REMATCH",
                    },
                )
                db.add(audit)
                await db.commit()

                return ReviewMutationResponseDTO(
                    status="NEEDS_REMATCH",
                    message=f"Progress event work description edited. Match invalidated for [{act_code}]; status set to NEEDS_REMATCH.",
                    candidate_id=candidate.id,
                    activity_code=act_code,
                    action="EDITED",
                    audit_id=audit.id,
                )
            else:
                # Re-run fresh Phase 3 deterministic validation
                val_res = await DependencyValidatorService.validate_candidate(db, candidate.id)

                audit = ReviewAudit(
                    project_id=project_id,
                    match_candidate_id=candidate.id,
                    progress_event_id=event.id,
                    activity_id=candidate.activity_id,
                    activity_code=act_code,
                    action="EDITED",
                    decision="EDIT",
                    reviewer_user=reviewer_user,
                    review_timestamp=datetime.now(timezone.utc),
                    remarks=payload.reason or "Engineer edited event progress parameters.",
                    is_override=False,
                    previous_values={},
                    new_values={
                        "quantity_reported": event.quantity_reported,
                        "uom": event.uom,
                        "event_date": str(event.event_date) if event.event_date else None,
                        "status_claim": event.status_claim,
                        "final_decision": val_res.final_decision,
                    },
                )
                db.add(audit)
                await db.commit()

                return ReviewMutationResponseDTO(
                    status="EDITED",
                    message=f"Progress event edited and re-validated (Result: {val_res.final_decision}).",
                    candidate_id=candidate.id,
                    activity_code=val_res.activity_code,
                    action="EDITED",
                    audit_id=audit.id,
                )
        except Exception as e:
            await db.rollback()
            logger.error(f"Transaction failed during edit_progress_event: {e}")
            raise

    @staticmethod
    async def list_audit_logs(
        db: AsyncSession,
        project_id: Optional[str] = None,
        activity_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ReviewAuditLogDTO]:
        """Retrieves logged review and mutation audit records."""
        query = select(ReviewAudit)
        if project_id:
            query = query.where(ReviewAudit.project_id == project_id)
        if activity_id:
            query = query.where(ReviewAudit.activity_id == activity_id)
        if action and action != "ALL":
            query = query.where(ReviewAudit.action == action)

        query = query.order_by(desc(ReviewAudit.review_timestamp)).limit(limit).offset(offset)
        res = await db.execute(query)
        audits = list(res.scalars().all())

        return [ReviewAuditLogDTO.model_validate(a) for a in audits]

    @staticmethod
    async def get_dashboard_stats(
        db: AsyncSession, project_id: Optional[str] = None
    ) -> DashboardStatsDTO:
        """Aggregates executive KPIs for dashboard monitoring."""
        # 1. Total reports
        rep_q = select(func.count(FieldReport.id))
        if project_id:
            rep_q = rep_q.where(FieldReport.project_id == project_id)
        rep_count = (await db.execute(rep_q)).scalar() or 0

        # 2. Total progress events
        evt_q = select(func.count(ProgressEvent.id)).join(FieldReport, ProgressEvent.field_report_id == FieldReport.id)
        if project_id:
            evt_q = evt_q.where(FieldReport.project_id == project_id)
        evt_count = (await db.execute(evt_q)).scalar() or 0

        # 3. Candidates by status
        cand_q = (
            select(ActivityMatchCandidate.status, func.count(ActivityMatchCandidate.id))
            .join(ProgressEvent, ActivityMatchCandidate.progress_event_id == ProgressEvent.id)
            .join(FieldReport, ProgressEvent.field_report_id == FieldReport.id)
        )
        if project_id:
            cand_q = cand_q.where(FieldReport.project_id == project_id)
        cand_q = cand_q.group_by(ActivityMatchCandidate.status)
        cand_rows = (await db.execute(cand_q)).all()
        status_map = {status: count for status, count in cand_rows}

        # 4. Total mutations & last update
        audit_q = select(ReviewAudit).where(ReviewAudit.action.in_(["APPROVED", "OVERRIDDEN", "APPLIED"]))
        if project_id:
            audit_q = audit_q.where(ReviewAudit.project_id == project_id)
        audit_q = audit_q.order_by(desc(ReviewAudit.review_timestamp))
        last_audit = (await db.execute(audit_q.limit(1))).scalar_one_or_none()

        # 5. Total violations
        viol_q = select(func.count(DependencyViolation.id))
        if project_id:
            viol_q = viol_q.where(DependencyViolation.project_id == project_id)
        total_viols = (await db.execute(viol_q)).scalar() or 0

        last_update = None
        if last_audit:
            last_update = {
                "activity_code": last_audit.activity_code,
                "action": last_audit.action,
                "actor": last_audit.reviewer_user,
                "timestamp": str(last_audit.review_timestamp),
                "is_override": last_audit.is_override,
            }

        return DashboardStatsDTO(
            total_reports=rep_count,
            total_events=evt_count,
            auto_matched=status_map.get("AUTO_MATCHED", 0),
            needs_review=status_map.get("NEEDS_REVIEW", 0),
            blocked_by_dependency=status_map.get("BLOCKED_BY_DEPENDENCY", 0),
            applied=status_map.get("APPLIED", 0),
            rejected=status_map.get("REJECTED", 0),
            total_mutations=status_map.get("APPLIED", 0),
            total_violations=total_viols,
            unresolved_violations=total_viols,
            last_update=last_update,
        )
