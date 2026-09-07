from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ViolationItem(BaseModel):
    violation_type: str  # PREDECESSOR_INCOMPLETE, OUT_OF_SEQUENCE, QUANTITY_OVERRUN, DEPENDENCY_CYCLE, CRITICAL_PATH_RISK
    severity: str  # HARD_VIOLATION, SOFT_WARNING
    description: str
    predecessor_id: Optional[str] = None
    predecessor_code: Optional[str] = None
    successor_id: Optional[str] = None
    successor_code: Optional[str] = None
    expected_condition: Optional[str] = None
    observed_condition: Optional[str] = None


def is_activity_complete(act: Any) -> bool:
    """Check if an activity is physically completed."""
    actual_finish = getattr(act, "actual_finish", None) or (act.get("actual_finish") if isinstance(act, dict) else None)
    if actual_finish is not None:
        return True

    pct = getattr(act, "physical_percent_complete", 0.0) or (act.get("physical_percent_complete", 0.0) if isinstance(act, dict) else 0.0)
    if pct >= 100.0:
        return True

    planned_qty = getattr(act, "planned_quantity", 0.0) or (act.get("planned_quantity", 0.0) if isinstance(act, dict) else 0.0)
    actual_qty = getattr(act, "actual_quantity", 0.0) or (act.get("actual_quantity", 0.0) if isinstance(act, dict) else 0.0)
    if planned_qty > 0 and actual_qty >= planned_qty:
        return True

    return False


def is_activity_started(act: Any) -> bool:
    """Check if an activity has commenced execution."""
    if is_activity_complete(act):
        return True

    actual_start = getattr(act, "actual_start", None) or (act.get("actual_start") if isinstance(act, dict) else None)
    if actual_start is not None:
        return True

    pct = getattr(act, "physical_percent_complete", 0.0) or (act.get("physical_percent_complete", 0.0) if isinstance(act, dict) else 0.0)
    if pct > 0:
        return True

    actual_qty = getattr(act, "actual_quantity", 0.0) or (act.get("actual_quantity", 0.0) if isinstance(act, dict) else 0.0)
    if actual_qty > 0:
        return True

    return False


def validate_predecessors_complete(
    activity: Any, event: Any, graph: Any
) -> List[ViolationItem]:
    """
    Validates that required predecessors satisfy relationship completion constraints (FS, SS, FF, SF).
    """
    violations: List[ViolationItem] = []
    act_id = getattr(activity, "id", None) or activity.get("id")
    act_code = getattr(activity, "activity_code", None) or activity.get("activity_code", act_id)
    status_claim = getattr(event, "status_claim", "IN_PROGRESS") or "IN_PROGRESS"

    predecessors = graph.get_predecessors(act_id)

    for pred_node, dep_type, lag_days in predecessors:
        pred_id = getattr(pred_node, "id", None) or pred_node.get("id")
        pred_code = getattr(pred_node, "activity_code", None) or pred_node.get("activity_code", pred_id)
        pred_name = getattr(pred_node, "name", None) or pred_node.get("name", "")
        pred_pct = getattr(pred_node, "physical_percent_complete", 0.0) or pred_node.get("physical_percent_complete", 0.0) if isinstance(pred_node, dict) else 0.0

        # Rule A1: Finish-to-Start (FS)
        # Predecessor MUST be 100% finished before successor can start or complete
        if dep_type == "FS":
            if not is_activity_complete(pred_node):
                violations.append(
                    ViolationItem(
                        violation_type="PREDECESSOR_INCOMPLETE",
                        severity="HARD_VIOLATION",
                        description=(
                            f"Required predecessor [{pred_code}] '{pred_name}' is incomplete. "
                            f"Successor [{act_code}] cannot commence under Finish-to-Start (FS) dependency constraint."
                        ),
                        predecessor_id=pred_id,
                        predecessor_code=pred_code,
                        successor_id=act_id,
                        successor_code=act_code,
                        expected_condition=f"Predecessor [{pred_code}] must be 100% complete (actual_finish is set) before [{act_code}] can commence.",
                        observed_condition=f"Predecessor [{pred_code}] actual_finish is null (progress: {pred_pct}%).",
                    )
                )

        # Rule A2: Start-to-Start (SS)
        # Predecessor MUST have started before successor can start
        elif dep_type == "SS":
            if not is_activity_started(pred_node):
                violations.append(
                    ViolationItem(
                        violation_type="PREDECESSOR_INCOMPLETE",
                        severity="HARD_VIOLATION",
                        description=(
                            f"Required predecessor [{pred_code}] '{pred_name}' has not commenced. "
                            f"Successor [{act_code}] cannot start under Start-to-Start (SS) dependency constraint."
                        ),
                        predecessor_id=pred_id,
                        predecessor_code=pred_code,
                        successor_id=act_id,
                        successor_code=act_code,
                        expected_condition=f"Predecessor [{pred_code}] must commence execution before [{act_code}] can start.",
                        observed_condition=f"Predecessor [{pred_code}] has not started.",
                    )
                )

        # Rule A3: Finish-to-Finish (FF)
        # If successor claims completion, predecessor must also be complete
        elif dep_type == "FF":
            if status_claim in ("MILESTONE_COMPLETED", "COMPLETED") and not is_activity_complete(pred_node):
                violations.append(
                    ViolationItem(
                        violation_type="PREDECESSOR_INCOMPLETE",
                        severity="HARD_VIOLATION",
                        description=(
                            f"Predecessor [{pred_code}] '{pred_name}' is not finished. "
                            f"Successor [{act_code}] cannot claim completion under Finish-to-Finish (FF) dependency constraint."
                        ),
                        predecessor_id=pred_id,
                        predecessor_code=pred_code,
                        successor_id=act_id,
                        successor_code=act_code,
                        expected_condition=f"Predecessor [{pred_code}] must be finished before [{act_code}] can complete.",
                        observed_condition=f"Predecessor [{pred_code}] is incomplete.",
                    )
                )

        # Rule A4: Start-to-Finish (SF)
        elif dep_type == "SF":
            if status_claim in ("MILESTONE_COMPLETED", "COMPLETED") and not is_activity_started(pred_node):
                violations.append(
                    ViolationItem(
                        violation_type="PREDECESSOR_INCOMPLETE",
                        severity="HARD_VIOLATION",
                        description=(
                            f"Predecessor [{pred_code}] '{pred_name}' has not commenced. "
                            f"Successor [{act_code}] cannot complete under Start-to-Finish (SF) dependency constraint."
                        ),
                        predecessor_id=pred_id,
                        predecessor_code=pred_code,
                        successor_id=act_id,
                        successor_code=act_code,
                        expected_condition=f"Predecessor [{pred_code}] must start before [{act_code}] can complete.",
                        observed_condition=f"Predecessor [{pred_code}] has not started.",
                    )
                )

    return violations


def validate_sequence_and_lags(
    activity: Any, event: Any, graph: Any
) -> List[ViolationItem]:
    """
    Validates that reported progress dates adhere to chronological dependency sequencing and lags.
    """
    violations: List[ViolationItem] = []
    act_id = getattr(activity, "id", None) or activity.get("id")
    act_code = getattr(activity, "activity_code", None) or activity.get("activity_code", act_id)
    event_date = getattr(event, "event_date", None) or (event.get("event_date") if isinstance(event, dict) else None)

    if not event_date:
        return violations

    predecessors = graph.get_predecessors(act_id)

    for pred_node, dep_type, lag_days in predecessors:
        pred_id = getattr(pred_node, "id", None) or pred_node.get("id")
        pred_code = getattr(pred_node, "activity_code", None) or pred_node.get("activity_code", pred_id)
        pred_finish = getattr(pred_node, "actual_finish", None) or (pred_node.get("actual_finish") if isinstance(pred_node, dict) else None)
        pred_start = getattr(pred_node, "actual_start", None) or (pred_node.get("actual_start") if isinstance(pred_node, dict) else None)

        # 1. FS sequencing
        if dep_type == "FS" and pred_finish is not None:
            min_allowed_date = pred_finish + timedelta(days=lag_days)
            if event_date < min_allowed_date:
                violations.append(
                    ViolationItem(
                        violation_type="OUT_OF_SEQUENCE",
                        severity="HARD_VIOLATION",
                        description=(
                            f"Out-of-sequence progress: Reported execution date ({event_date}) for [{act_code}] "
                            f"precedes predecessor [{pred_code}] actual completion date ({pred_finish}) + {lag_days} days lag."
                        ),
                        predecessor_id=pred_id,
                        predecessor_code=pred_code,
                        successor_id=act_id,
                        successor_code=act_code,
                        expected_condition=f"Execution date must be >= {min_allowed_date} (predecessor actual finish + {lag_days}d lag).",
                        observed_condition=f"Reported execution date is {event_date} (early by {(min_allowed_date - event_date).days} days).",
                    )
                )

        # 2. SS sequencing
        elif dep_type == "SS" and pred_start is not None:
            min_allowed_date = pred_start + timedelta(days=lag_days)
            if event_date < min_allowed_date:
                violations.append(
                    ViolationItem(
                        violation_type="OUT_OF_SEQUENCE",
                        severity="HARD_VIOLATION",
                        description=(
                            f"Out-of-sequence progress: Reported date ({event_date}) for [{act_code}] "
                            f"precedes required Start-to-Start offset ({min_allowed_date}) from [{pred_code}]."
                        ),
                        predecessor_id=pred_id,
                        predecessor_code=pred_code,
                        successor_id=act_id,
                        successor_code=act_code,
                        expected_condition=f"Execution date must be >= {min_allowed_date} (predecessor actual start + {lag_days}d lag).",
                        observed_condition=f"Reported date is {event_date} (early by {(min_allowed_date - event_date).days} days).",
                    )
                )

        # 3. FF sequencing
        elif dep_type == "FF" and pred_finish is not None:
            min_allowed_date = pred_finish + timedelta(days=lag_days)
            if event_date < min_allowed_date:
                violations.append(
                    ViolationItem(
                        violation_type="OUT_OF_SEQUENCE",
                        severity="HARD_VIOLATION",
                        description=(
                            f"Out-of-sequence progress: Reported finish ({event_date}) for [{act_code}] "
                            f"precedes required Finish-to-Finish offset ({min_allowed_date}) from [{pred_code}]."
                        ),
                        predecessor_id=pred_id,
                        predecessor_code=pred_code,
                        successor_id=act_id,
                        successor_code=act_code,
                        expected_condition=f"Completion date must be >= {min_allowed_date} (predecessor actual finish + {lag_days}d lag).",
                        observed_condition=f"Reported date is {event_date}.",
                    )
                )

    return violations


def validate_quantity_overrun(activity: Any, event: Any) -> List[ViolationItem]:
    """
    Validates that reported progress does not breach planned quantity boundaries.
    """
    violations: List[ViolationItem] = []
    act_id = getattr(activity, "id", None) or activity.get("id")
    act_code = getattr(activity, "activity_code", None) or activity.get("activity_code", act_id)

    planned_qty = getattr(activity, "planned_quantity", 0.0) or (activity.get("planned_quantity", 0.0) if isinstance(activity, dict) else 0.0)
    actual_qty = getattr(activity, "actual_quantity", 0.0) or (activity.get("actual_quantity", 0.0) if isinstance(activity, dict) else 0.0)
    uom = getattr(activity, "uom", "UNITS") or (activity.get("uom", "UNITS") if isinstance(activity, dict) else "UNITS")

    event_qty = getattr(event, "quantity_reported", None)
    if event_qty is None and isinstance(event, dict):
        event_qty = event.get("quantity_reported")

    if planned_qty > 0 and event_qty is not None:
        proposed_total = actual_qty + event_qty
        overrun_ratio = proposed_total / planned_qty

        # Severe quantity overrun (> 15%) -> HARD_VIOLATION
        if overrun_ratio > 1.15:
            overrun_pct = (overrun_ratio - 1.0) * 100
            violations.append(
                ViolationItem(
                    violation_type="QUANTITY_OVERRUN",
                    severity="HARD_VIOLATION",
                    description=(
                        f"Major quantity overrun: Proposed progress ({event_qty} {uom}) brings total to "
                        f"{proposed_total} {uom}, exceeding planned scope ({planned_qty} {uom}) by {overrun_pct:.1f}%."
                    ),
                    successor_id=act_id,
                    successor_code=act_code,
                    expected_condition=f"Cumulative actual quantity <= planned quantity ({planned_qty} {uom}).",
                    observed_condition=f"Proposed cumulative quantity ({proposed_total} {uom}) exceeds planned budget by {overrun_pct:.1f}%.",
                )
            )
        # Moderate quantity overrun (2% - 15%) -> SOFT_WARNING
        elif overrun_ratio > 1.02:
            overrun_pct = (overrun_ratio - 1.0) * 100
            violations.append(
                ViolationItem(
                    violation_type="QUANTITY_OVERRUN",
                    severity="SOFT_WARNING",
                    description=(
                        f"Quantity overrun warning: Proposed progress ({event_qty} {uom}) brings total to "
                        f"{proposed_total} {uom}, exceeding planned scope ({planned_qty} {uom}) by {overrun_pct:.1f}%."
                    ),
                    successor_id=act_id,
                    successor_code=act_code,
                    expected_condition=f"Reported quantity within planned bounds ({planned_qty} {uom}).",
                    observed_condition=f"Proposed cumulative quantity ({proposed_total} {uom}) exceeds planned by {overrun_pct:.1f}%.",
                )
            )

    return violations


def validate_critical_path_impact(
    activity: Any, event: Any, cpm_metrics: Dict[str, Dict[str, Any]], existing_violations: List[ViolationItem]
) -> List[ViolationItem]:
    """
    Detects whether schedule risks directly threaten the project's critical path.
    """
    violations: List[ViolationItem] = []
    act_id = getattr(activity, "id", None) or activity.get("id")
    act_code = getattr(activity, "activity_code", None) or activity.get("activity_code", act_id)

    metrics = cpm_metrics.get(act_id, {})
    total_float = metrics.get("total_float", getattr(activity, "total_float_days", 0))
    is_critical = metrics.get("is_critical", getattr(activity, "is_critical", False))

    if is_critical or total_float <= 0:
        has_blocker = any(v.severity == "HARD_VIOLATION" for v in existing_violations)
        if has_blocker:
            violations.append(
                ViolationItem(
                    violation_type="CRITICAL_PATH_RISK",
                    severity="HARD_VIOLATION",
                    description=(
                        f"Critical path activity [{act_code}] has unresolved dependency violations. "
                        f"With zero total float (Float: 0 days), any delay directly pushes project completion."
                    ),
                    successor_id=act_id,
                    successor_code=act_code,
                    expected_condition="Critical path milestones must have zero dependency impediments.",
                    observed_condition="Critical path milestone is blocked by incomplete or out-of-sequence predecessors.",
                )
            )

    return violations


def validate_graph_acyclic(graph: Any) -> List[ViolationItem]:
    """
    Validates that the dependency network does not contain invalid circular dependencies.
    """
    violations: List[ViolationItem] = []
    cycles = graph.detect_cycles()
    for cycle in cycles:
        cycle_str = " -> ".join(cycle)
        violations.append(
            ViolationItem(
                violation_type="DEPENDENCY_CYCLE",
                severity="HARD_VIOLATION",
                description=f"Circular dependency detected in schedule network: {cycle_str}. Schedule network must be a strictly acyclic DAG.",
                expected_condition="Schedule network must be a Directed Acyclic Graph (DAG) with zero cycles.",
                observed_condition=f"Circular dependency path: {cycle_str}.",
            )
        )
    return violations
