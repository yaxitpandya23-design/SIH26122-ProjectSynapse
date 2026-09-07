import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, desc

from app.modules.schedules.models import Project, ScheduleVersion, ScheduleActivity, ActivityDependency
from app.modules.field_capture.models import ProgressEvent
from app.modules.semantic_matcher.models import ActivityMatchCandidate
from app.modules.dependency_validator.models import DependencyViolation
from app.modules.dependency_validator.schemas import (
    DependencyViolationDTO,
    ValidationResultDTO,
    DependencyGraphDTO,
    GraphNodeDTO,
    GraphEdgeDTO,
)
from app.modules.dependency_validator.graph import ScheduleDependencyGraph
from app.modules.dependency_validator.rules import (
    validate_predecessors_complete,
    validate_sequence_and_lags,
    validate_quantity_overrun,
    validate_critical_path_impact,
    validate_graph_acyclic,
    ViolationItem,
)

logger = logging.getLogger("synapse.dependency_validator.service")


class DependencyValidatorService:
    """
    Deterministic Schedule and Dependency Validation Engine.
    Operates as the authoritative gateway between semantic matching and schedule modification.
    """

    @staticmethod
    async def build_graph_for_version(
        db: AsyncSession, schedule_version_id: str
    ) -> ScheduleDependencyGraph:
        """Constructs a ScheduleDependencyGraph for a given schedule version."""
        act_res = await db.execute(
            select(ScheduleActivity).where(ScheduleActivity.schedule_version_id == schedule_version_id)
        )
        activities = list(act_res.scalars().all())

        dep_res = await db.execute(
            select(ActivityDependency).where(ActivityDependency.schedule_version_id == schedule_version_id)
        )
        dependencies = list(dep_res.scalars().all())

        return ScheduleDependencyGraph(activities=activities, dependencies=dependencies)

    @staticmethod
    async def validate_candidate(
        db: AsyncSession, candidate_id: str
    ) -> ValidationResultDTO:
        """
        Validates a single candidate against deterministic dependency, sequence, and quantity constraints.
        Persists violations and updates the candidate's final decision status.
        """
        cand_res = await db.execute(
            select(ActivityMatchCandidate).where(ActivityMatchCandidate.id == candidate_id)
        )
        candidate = cand_res.scalar_one_or_none()
        if not candidate:
            raise ValueError(f"Match candidate '{candidate_id}' not found.")

        # Fetch activity and progress event
        act_res = await db.execute(
            select(ScheduleActivity).where(ScheduleActivity.id == candidate.activity_id)
        )
        activity = act_res.scalar_one_or_none()
        if not activity:
            raise ValueError(f"ScheduleActivity '{candidate.activity_id}' not found.")

        event_res = await db.execute(
            select(ProgressEvent).where(ProgressEvent.id == candidate.progress_event_id)
        )
        event = event_res.scalar_one_or_none()
        if not event:
            raise ValueError(f"ProgressEvent '{candidate.progress_event_id}' not found.")

        # Fetch project_id
        ver_res = await db.execute(
            select(ScheduleVersion).where(ScheduleVersion.id == activity.schedule_version_id)
        )
        version = ver_res.scalar_one_or_none()
        project_id = version.project_id if version else None

        # 1. Build Graph & Compute CPM
        graph = await DependencyValidatorService.build_graph_for_version(db, activity.schedule_version_id)
        cpm_metrics = graph.compute_cpm()

        # 2. Execute Deterministic Validation Rules
        rule_violations: List[ViolationItem] = []

        # Rule E: Acyclic DAG Verification
        rule_violations.extend(validate_graph_acyclic(graph))

        # Rule A: Incomplete Predecessors
        rule_violations.extend(validate_predecessors_complete(activity, event, graph))

        # Rule B: Out of Sequence Progress & Lags
        rule_violations.extend(validate_sequence_and_lags(activity, event, graph))

        # Rule C: Quantity Overrun
        rule_violations.extend(validate_quantity_overrun(activity, event))

        # Rule D: Critical Path & Float Impact
        rule_violations.extend(
            validate_critical_path_impact(activity, event, cpm_metrics, rule_violations)
        )

        has_hard_violations = any(v.severity == "HARD_VIOLATION" for v in rule_violations)
        has_soft_warnings = any(v.severity == "SOFT_WARNING" for v in rule_violations)

        # 3. Determine Final Decision Status
        # Semantic decision was: candidate.status or derived from confidence score
        score = candidate.confidence_score
        semantic_decision = "AUTO_MATCHED" if score >= 0.85 else ("NEEDS_REVIEW" if score >= 0.50 else "UNMATCHED")

        if candidate.status == "UNMATCHED" or score < 0.50 or semantic_decision == "UNMATCHED":
            final_decision = "UNMATCHED"
            summary = "Validation SKIPPED: Semantic match score is below minimum threshold (<0.50). Candidate is UNMATCHED."
        elif has_hard_violations:
            final_decision = "BLOCKED_BY_DEPENDENCY"
            summary = (
                f"Validation FAILED: Blocked by {sum(1 for v in rule_violations if v.severity == 'HARD_VIOLATION')} "
                f"hard dependency/schedule violation(s)."
            )
        elif has_soft_warnings:
            final_decision = "NEEDS_REVIEW"
            summary = (
                f"Validation WARNING: {sum(1 for v in rule_violations if v.severity == 'SOFT_WARNING')} "
                f"schedule advisory warning(s) flagged for human review."
            )
        else:
            final_decision = semantic_decision
            summary = "Validation PASSED: All predecessor relationships, sequence bounds, and quantity limits verified."

        # Update candidate status in DB
        candidate.status = final_decision
        candidate.validated_activity_version = getattr(activity, "actuals_version", 1)

        # 4. Persist Violations to DB
        # Remove previous violations for this candidate to prevent duplicates
        await db.execute(
            delete(DependencyViolation).where(
                DependencyViolation.match_candidate_id == candidate.id
            )
        )

        persisted_violations: List[DependencyViolationDTO] = []
        for v in rule_violations:
            violation_record = DependencyViolation(
                project_id=project_id,
                progress_event_id=event.id,
                match_candidate_id=candidate.id,
                activity_id=activity.id,
                activity_code=activity.activity_code,
                predecessor_activity_id=v.predecessor_id,
                predecessor_activity_code=v.predecessor_code,
                successor_activity_id=v.successor_id,
                successor_activity_code=v.successor_code,
                violation_type=v.violation_type,
                severity=v.severity,
                description=v.description,
                expected_condition=v.expected_condition,
                observed_condition=v.observed_condition,
                detected_at=datetime.now(timezone.utc),
            )
            db.add(violation_record)
            await db.flush()

            persisted_violations.append(
                DependencyViolationDTO(
                    id=violation_record.id,
                    project_id=project_id,
                    progress_event_id=event.id,
                    match_candidate_id=candidate.id,
                    activity_id=activity.id,
                    activity_code=activity.activity_code,
                    predecessor_activity_id=v.predecessor_id,
                    predecessor_activity_code=v.predecessor_code,
                    successor_activity_id=v.successor_id,
                    successor_activity_code=v.successor_code,
                    violation_type=v.violation_type,
                    severity=v.severity,
                    description=v.description,
                    expected_condition=v.expected_condition,
                    observed_condition=v.observed_condition,
                    detected_at=violation_record.detected_at,
                )
            )

        await db.commit()

        metrics = cpm_metrics.get(activity.id, {})

        return ValidationResultDTO(
            candidate_id=candidate.id,
            activity_id=activity.id,
            activity_code=activity.activity_code,
            activity_name=activity.name,
            confidence_score=candidate.confidence_score,
            semantic_decision=semantic_decision,
            final_decision=final_decision,
            has_hard_violations=has_hard_violations,
            has_soft_warnings=has_soft_warnings,
            violations=persisted_violations,
            is_critical_path=metrics.get("is_critical", activity.is_critical),
            total_float_days=metrics.get("total_float", activity.total_float_days),
            summary_reason=summary,
            validated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    async def validate_progress_event(
        db: AsyncSession, progress_event_id: str
    ) -> List[ValidationResultDTO]:
        """
        Runs validation across all match candidates for a given progress event.
        """
        cand_res = await db.execute(
            select(ActivityMatchCandidate)
            .where(ActivityMatchCandidate.progress_event_id == progress_event_id)
            .order_by(desc(ActivityMatchCandidate.confidence_score))
        )
        candidates = list(cand_res.scalars().all())

        results = []
        for cand in candidates:
            res = await DependencyValidatorService.validate_candidate(db, cand.id)
            results.append(res)

        return results

    @staticmethod
    async def get_project_graph(
        db: AsyncSession, project_id: str
    ) -> DependencyGraphDTO:
        """Retrieves and calculates CPM graph metrics for a project."""
        # Find active or latest schedule version
        ver_res = await db.execute(
            select(ScheduleVersion)
            .where(ScheduleVersion.project_id == project_id)
            .order_by(desc(ScheduleVersion.imported_at))
        )
        version = ver_res.scalars().first()
        if not version:
            raise ValueError(f"No schedule version found for project '{project_id}'.")

        graph = await DependencyValidatorService.build_graph_for_version(db, version.id)
        cpm_metrics = graph.compute_cpm()
        cycles = graph.detect_cycles()

        try:
            topo = [graph.id_to_code.get(nid, nid) for nid in graph.topological_sort()]
        except ValueError:
            topo = []

        nodes: List[GraphNodeDTO] = []
        critical_activities: List[str] = []

        for node_id, act in graph.nodes.items():
            metrics = cpm_metrics.get(node_id, {})
            is_crit = metrics.get("is_critical", False)
            act_code = getattr(act, "activity_code", node_id)
            if is_crit:
                critical_activities.append(act_code)

            nodes.append(
                GraphNodeDTO(
                    id=node_id,
                    activity_code=act_code,
                    name=getattr(act, "name", ""),
                    discipline=getattr(act, "discipline", "GENERAL"),
                    duration_days=getattr(act, "planned_duration_days", 0),
                    early_start=str(metrics.get("early_start")),
                    early_finish=str(metrics.get("early_finish")),
                    late_start=str(metrics.get("late_start")),
                    late_finish=str(metrics.get("late_finish")),
                    total_float_days=metrics.get("total_float", 0),
                    is_critical=is_crit,
                    status="COMPLETED" if getattr(act, "actual_finish", None) else (
                        "IN_PROGRESS" if getattr(act, "actual_start", None) else "NOT_STARTED"
                    ),
                )
            )

        edges: List[GraphEdgeDTO] = []
        for u in graph.nodes:
            for edge in graph.adj.get(u, []):
                edges.append(
                    GraphEdgeDTO(
                        predecessor_id=edge.predecessor_id,
                        successor_id=edge.successor_id,
                        predecessor_code=graph.id_to_code.get(edge.predecessor_id, edge.predecessor_id),
                        successor_code=graph.id_to_code.get(edge.successor_id, edge.successor_id),
                        dependency_type=edge.dependency_type,
                        lag_days=edge.lag_days,
                    )
                )

        proj_duration = max((m.get("early_finish", 0) for m in cpm_metrics.values()), default=0)

        return DependencyGraphDTO(
            project_id=project_id,
            schedule_version_id=version.id,
            nodes=nodes,
            edges=edges,
            has_cycles=len(cycles) > 0,
            cycles=cycles,
            topological_order=topo,
            critical_path_activities=critical_activities,
            project_duration_days=proj_duration,
        )

    @staticmethod
    async def list_violations(
        db: AsyncSession,
        project_id: Optional[str] = None,
        progress_event_id: Optional[str] = None,
        activity_id: Optional[str] = None,
        severity: Optional[str] = None,
        violation_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[DependencyViolationDTO]:
        """Lists dependency violations with multi-field filtering."""
        query = select(DependencyViolation).order_by(desc(DependencyViolation.detected_at))

        if project_id:
            query = query.where(DependencyViolation.project_id == project_id)
        if progress_event_id:
            query = query.where(DependencyViolation.progress_event_id == progress_event_id)
        if activity_id:
            query = query.where(DependencyViolation.activity_id == activity_id)
        if severity:
            query = query.where(DependencyViolation.severity == severity.upper())
        if violation_type:
            query = query.where(DependencyViolation.violation_type == violation_type.upper())

        query = query.limit(limit)
        res = await db.execute(query)
        violations = list(res.scalars().all())

        dtos = []
        for v in violations:
            dtos.append(
                DependencyViolationDTO(
                    id=v.id,
                    project_id=v.project_id,
                    progress_event_id=v.progress_event_id,
                    match_candidate_id=v.match_candidate_id,
                    activity_id=v.activity_id,
                    activity_code=v.activity_code,
                    predecessor_activity_id=v.predecessor_activity_id,
                    predecessor_activity_code=v.predecessor_activity_code,
                    successor_activity_id=v.successor_activity_id,
                    successor_activity_code=v.successor_activity_code,
                    violation_type=v.violation_type,
                    severity=v.severity,
                    description=v.description,
                    expected_condition=v.expected_condition,
                    observed_condition=v.observed_condition,
                    detected_at=v.detected_at,
                )
            )
        return dtos
