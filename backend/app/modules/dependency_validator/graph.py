import logging
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set, Tuple, Any

logger = logging.getLogger("synapse.dependency_validator.graph")


class DependencyEdge:
    def __init__(self, predecessor_id: str, successor_id: str, dependency_type: str = "FS", lag_days: int = 0):
        self.predecessor_id = predecessor_id
        self.successor_id = successor_id
        self.dependency_type = dependency_type.upper().strip()  # FS, SS, FF, SF
        self.lag_days = lag_days

    def __repr__(self):
        return f"Edge({self.predecessor_id} -[{self.dependency_type}:{self.lag_days}d]-> {self.successor_id})"


class ScheduleDependencyGraph:
    """
    Deterministic Directed Acyclic Graph (DAG) representing the schedule's
    activity network and dependency constraints.
    Supports FS, SS, FF, SF relationships with lags, topological ordering,
    3-color cycle detection, and Critical Path Method (CPM) float calculations.
    """

    def __init__(self, activities: List[Any], dependencies: List[Any]):
        self.nodes: Dict[str, Any] = {}
        self.code_to_id: Dict[str, str] = {}
        self.id_to_code: Dict[str, str] = {}

        # Adjacency maps
        self.adj: Dict[str, List[DependencyEdge]] = defaultdict(list)       # pred -> [edges to succs]
        self.rev_adj: Dict[str, List[DependencyEdge]] = defaultdict(list)   # succ -> [edges from preds]

        # Ingest activities (nodes)
        for act in activities:
            act_id = getattr(act, "id", None) or (act.get("id") if isinstance(act, dict) else None)
            act_code = getattr(act, "activity_code", None) or (act.get("activity_code") if isinstance(act, dict) else act_id)
            self.nodes[act_id] = act
            self.code_to_id[act_code] = act_id
            self.id_to_code[act_id] = act_code

        # Ingest dependencies (edges)
        for dep in dependencies:
            p_id = getattr(dep, "predecessor_id", None) or (dep.get("predecessor_id") if isinstance(dep, dict) else None)
            s_id = getattr(dep, "successor_id", None) or (dep.get("successor_id") if isinstance(dep, dict) else None)
            dep_type = getattr(dep, "dependency_type", None) or (dep.get("dependency_type") if isinstance(dep, dict) else "FS") or "FS"
            lag = getattr(dep, "lag_days", None)
            if lag is None and isinstance(dep, dict):
                lag = dep.get("lag_days", 0)
            lag = int(lag or 0)

            if p_id in self.nodes and s_id in self.nodes:
                edge = DependencyEdge(p_id, s_id, dep_type, lag)
                self.adj[p_id].append(edge)
                self.rev_adj[s_id].append(edge)

    def get_predecessors(self, activity_id: str) -> List[Tuple[Any, str, int]]:
        """Returns list of (predecessor_node, dependency_type, lag_days)."""
        results = []
        for edge in self.rev_adj.get(activity_id, []):
            pred_node = self.nodes.get(edge.predecessor_id)
            if pred_node:
                results.append((pred_node, edge.dependency_type, edge.lag_days))
        return results

    def get_successors(self, activity_id: str) -> List[Tuple[Any, str, int]]:
        """Returns list of (successor_node, dependency_type, lag_days)."""
        results = []
        for edge in self.adj.get(activity_id, []):
            succ_node = self.nodes.get(edge.successor_id)
            if succ_node:
                results.append((succ_node, edge.dependency_type, edge.lag_days))
        return results

    def detect_cycles(self) -> List[List[str]]:
        """
        Detects directed cycles in the activity network using 3-color DFS.
        Returns list of cycles represented as lists of activity codes.
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        colors: Dict[str, int] = {node_id: WHITE for node_id in self.nodes}
        parent: Dict[str, Optional[str]] = {node_id: None for node_id in self.nodes}
        cycles: List[List[str]] = []

        def dfs(u: str):
            colors[u] = GRAY
            for edge in self.adj.get(u, []):
                v = edge.successor_id
                if colors[v] == GRAY:
                    # Cycle detected: backtrack from u to v
                    cycle = [self.id_to_code.get(v, v)]
                    curr = u
                    while curr is not None and curr != v:
                        cycle.append(self.id_to_code.get(curr, curr))
                        curr = parent.get(curr)
                    cycle.append(self.id_to_code.get(v, v))
                    cycle.reverse()
                    cycles.append(cycle)
                elif colors[v] == WHITE:
                    parent[v] = u
                    dfs(v)
            colors[u] = BLACK

        for node_id in self.nodes:
            if colors[node_id] == WHITE:
                dfs(node_id)

        return cycles

    def topological_sort(self) -> List[str]:
        """
        Computes valid topological ordering using Kahn's algorithm.
        Returns list of activity IDs in valid execution order.
        Raises ValueError if the network contains cycles.
        """
        in_degree: Dict[str, int] = {node_id: 0 for node_id in self.nodes}
        for u in self.nodes:
            for edge in self.adj.get(u, []):
                in_degree[edge.successor_id] += 1

        queue = deque([node_id for node_id, deg in in_degree.items() if deg == 0])
        topo_order: List[str] = []

        while queue:
            u = queue.popleft()
            topo_order.append(u)
            for edge in self.adj.get(u, []):
                v = edge.successor_id
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

        if len(topo_order) != len(self.nodes):
            cycles = self.detect_cycles()
            raise ValueError(f"Dependency network contains cycles: {cycles}")

        return topo_order

    def compute_cpm(self) -> Dict[str, Dict[str, Any]]:
        """
        Executes Critical Path Method (CPM) forward and backward passes.
        Returns metrics per activity:
        {
           activity_id: {
               'early_start': int,
               'early_finish': int,
               'late_start': int,
               'late_finish': int,
               'total_float': int,
               'is_critical': bool
           }
        }
        """
        if not self.nodes:
            return {}

        try:
            topo_order = self.topological_sort()
        except ValueError:
            # If cycles exist, CPM cannot run deterministically
            return {
                node_id: {
                    "early_start": 0, "early_finish": 0, "late_start": 0, "late_finish": 0,
                    "total_float": 0, "is_critical": False
                }
                for node_id in self.nodes
            }

        def get_duration(node_id: str) -> int:
            node = self.nodes[node_id]
            dur = getattr(node, "planned_duration_days", None)
            if dur is None and isinstance(node, dict):
                dur = node.get("planned_duration_days", 0)
            return max(1, int(dur or 1))

        # 1. Forward Pass (Early Start & Early Finish)
        es: Dict[str, int] = {u: 0 for u in self.nodes}
        ef: Dict[str, int] = {}

        for u in topo_order:
            dur = get_duration(u)
            current_es = es[u]
            for edge in self.rev_adj.get(u, []):
                p = edge.predecessor_id
                p_ef = ef.get(p, es[p] + get_duration(p))
                p_es = es[p]
                dep_type = edge.dependency_type
                lag = edge.lag_days

                if dep_type == "FS":
                    req_es = p_ef + lag
                elif dep_type == "SS":
                    req_es = p_es + lag
                elif dep_type == "FF":
                    req_ef = p_ef + lag
                    req_es = req_ef - dur
                elif dep_type == "SF":
                    req_ef = p_es + lag
                    req_es = req_ef - dur
                else:
                    req_es = p_ef + lag

                current_es = max(current_es, req_es)

            es[u] = max(0, current_es)
            ef[u] = es[u] + dur

        project_finish = max(ef.values()) if ef else 0

        # 2. Backward Pass (Late Finish & Late Start)
        lf: Dict[str, int] = {u: project_finish for u in self.nodes}
        ls: Dict[str, int] = {}

        for u in reversed(topo_order):
            dur = get_duration(u)
            current_lf = lf[u]
            for edge in self.adj.get(u, []):
                s = edge.successor_id
                s_ls = ls.get(s, lf[s] - get_duration(s))
                s_lf = lf[s]
                dep_type = edge.dependency_type
                lag = edge.lag_days

                if dep_type == "FS":
                    req_lf = s_ls - lag
                elif dep_type == "SS":
                    req_ls = s_ls - lag
                    req_lf = req_ls + dur
                elif dep_type == "FF":
                    req_lf = s_lf - lag
                elif dep_type == "SF":
                    req_ls = s_lf - lag
                    req_lf = req_ls + dur
                else:
                    req_lf = s_ls - lag

                current_lf = min(current_lf, req_lf)

            lf[u] = current_lf
            ls[u] = lf[u] - dur

        # 3. Total Float and Critical Path Determination
        results: Dict[str, Dict[str, Any]] = {}
        for u in self.nodes:
            total_float = max(0, ls[u] - es[u])
            results[u] = {
                "early_start": es[u],
                "early_finish": ef[u],
                "late_start": ls[u],
                "late_finish": lf[u],
                "total_float": total_float,
                "is_critical": total_float == 0,
            }

        return results
