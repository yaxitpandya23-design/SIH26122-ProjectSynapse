import pytest
from app.modules.dependency_validator.graph import ScheduleDependencyGraph


def test_graph_construction_and_lookups():
    activities = [
        {"id": "act-1", "activity_code": "ACT-101", "name": "Survey", "planned_duration_days": 5},
        {"id": "act-2", "activity_code": "ACT-102", "name": "Excavation", "planned_duration_days": 10},
        {"id": "act-3", "activity_code": "ACT-103", "name": "Concrete", "planned_duration_days": 7},
    ]
    dependencies = [
        {"predecessor_id": "act-1", "successor_id": "act-2", "dependency_type": "FS", "lag_days": 2},
        {"predecessor_id": "act-2", "successor_id": "act-3", "dependency_type": "FS", "lag_days": 0},
    ]

    graph = ScheduleDependencyGraph(activities, dependencies)

    # Node count
    assert len(graph.nodes) == 3
    assert graph.code_to_id["ACT-101"] == "act-1"

    # Predecessor lookup for ACT-102
    preds_2 = graph.get_predecessors("act-2")
    assert len(preds_2) == 1
    assert preds_2[0][0]["activity_code"] == "ACT-101"
    assert preds_2[0][1] == "FS"
    assert preds_2[0][2] == 2

    # Successor lookup for ACT-102
    succs_2 = graph.get_successors("act-2")
    assert len(succs_2) == 1
    assert succs_2[0][0]["activity_code"] == "ACT-103"


def test_cycle_detection_positive_and_negative():
    # Acyclic graph
    activities = [
        {"id": "a", "activity_code": "ACT-A", "planned_duration_days": 3},
        {"id": "b", "activity_code": "ACT-B", "planned_duration_days": 4},
        {"id": "c", "activity_code": "ACT-C", "planned_duration_days": 5},
    ]
    deps_acyclic = [
        {"predecessor_id": "a", "successor_id": "b", "dependency_type": "FS", "lag_days": 0},
        {"predecessor_id": "b", "successor_id": "c", "dependency_type": "FS", "lag_days": 0},
    ]
    graph_ok = ScheduleDependencyGraph(activities, deps_acyclic)
    assert len(graph_ok.detect_cycles()) == 0

    # Circular graph (A -> B -> C -> A)
    deps_cyclic = [
        {"predecessor_id": "a", "successor_id": "b", "dependency_type": "FS", "lag_days": 0},
        {"predecessor_id": "b", "successor_id": "c", "dependency_type": "FS", "lag_days": 0},
        {"predecessor_id": "c", "successor_id": "a", "dependency_type": "FS", "lag_days": 0},
    ]
    graph_cyclic = ScheduleDependencyGraph(activities, deps_cyclic)
    cycles = graph_cyclic.detect_cycles()
    assert len(cycles) > 0
    # Ensure cycle path contains all 3 nodes
    cycle_nodes = set(cycles[0])
    assert {"ACT-A", "ACT-B", "ACT-C"}.issubset(cycle_nodes)


def test_topological_sort():
    activities = [
        {"id": "1", "activity_code": "ACT-1", "planned_duration_days": 2},
        {"id": "2", "activity_code": "ACT-2", "planned_duration_days": 3},
        {"id": "3", "activity_code": "ACT-3", "planned_duration_days": 4},
        {"id": "4", "activity_code": "ACT-4", "planned_duration_days": 5},
    ]
    deps = [
        {"predecessor_id": "1", "successor_id": "2", "dependency_type": "FS", "lag_days": 0},
        {"predecessor_id": "1", "successor_id": "3", "dependency_type": "FS", "lag_days": 0},
        {"predecessor_id": "2", "successor_id": "4", "dependency_type": "FS", "lag_days": 0},
        {"predecessor_id": "3", "successor_id": "4", "dependency_type": "FS", "lag_days": 0},
    ]
    graph = ScheduleDependencyGraph(activities, deps)
    order = graph.topological_sort()
    assert len(order) == 4
    # 1 must appear before 2 and 3; 2 and 3 before 4
    assert order.index("1") < order.index("2")
    assert order.index("1") < order.index("3")
    assert order.index("2") < order.index("4")
    assert order.index("3") < order.index("4")


def test_cpm_early_late_dates_and_critical_path():
    # Linear path: A (5d) -> B (10d) -> C (15d)
    # Parallel path: A (5d) -> D (5d) -> C (15d)
    activities = [
        {"id": "a", "activity_code": "ACT-A", "name": "Survey", "planned_duration_days": 5},
        {"id": "b", "activity_code": "ACT-B", "name": "Civil Mainline", "planned_duration_days": 10},
        {"id": "c", "activity_code": "ACT-C", "name": "Commissioning", "planned_duration_days": 15},
        {"id": "d", "activity_code": "ACT-D", "name": "Signage", "planned_duration_days": 5},
    ]
    deps = [
        {"predecessor_id": "a", "successor_id": "b", "dependency_type": "FS", "lag_days": 0},
        {"predecessor_id": "b", "successor_id": "c", "dependency_type": "FS", "lag_days": 0},
        {"predecessor_id": "a", "successor_id": "d", "dependency_type": "FS", "lag_days": 0},
        {"predecessor_id": "d", "successor_id": "c", "dependency_type": "FS", "lag_days": 0},
    ]
    graph = ScheduleDependencyGraph(activities, deps)
    cpm = graph.compute_cpm()

    # Total duration = 5 (A) + 10 (B) + 15 (C) = 30 days
    assert cpm["a"]["early_start"] == 0
    assert cpm["a"]["early_finish"] == 5
    assert cpm["b"]["early_start"] == 5
    assert cpm["b"]["early_finish"] == 15
    assert cpm["c"]["early_start"] == 15
    assert cpm["c"]["early_finish"] == 30

    # Path A-B-C is the Critical Path (Total Float = 0)
    assert cpm["a"]["is_critical"] is True
    assert cpm["b"]["is_critical"] is True
    assert cpm["c"]["is_critical"] is True
    assert cpm["a"]["total_float"] == 0
    assert cpm["b"]["total_float"] == 0
    assert cpm["c"]["total_float"] == 0

    # Activity D has total float = 5 days (Early finish 10, Late finish 15)
    assert cpm["d"]["total_float"] == 5
    assert cpm["d"]["is_critical"] is False


def test_dependency_relationships_and_lags_in_cpm():
    # Test SS with lag
    activities = [
        {"id": "1", "activity_code": "ACT-1", "planned_duration_days": 10},
        {"id": "2", "activity_code": "ACT-2", "planned_duration_days": 8},
    ]
    # ACT-2 starts 3 days after ACT-1 starts (SS:3)
    deps = [
        {"predecessor_id": "1", "successor_id": "2", "dependency_type": "SS", "lag_days": 3},
    ]
    graph = ScheduleDependencyGraph(activities, deps)
    cpm = graph.compute_cpm()

    assert cpm["1"]["early_start"] == 0
    assert cpm["2"]["early_start"] == 3
    assert cpm["2"]["early_finish"] == 11
