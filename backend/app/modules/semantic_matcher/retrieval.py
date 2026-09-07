import re
import math
from typing import List, Dict, Tuple, Optional
from app.modules.schedules.models import ScheduleActivity
from app.modules.field_capture.models import ProgressEvent
from app.modules.semantic_matcher.scoring import cosine_similarity


def tokenize(text: str) -> List[str]:
    """Tokenize and normalize text for sparse keyword indexing."""
    if not text:
        return []
    return re.findall(r'\b[a-zA-Z0-9_\-]{2,}\b', text.lower())


def compute_bm25_sparse_scores(
    query_text: str, activities: List[ScheduleActivity]
) -> Dict[str, float]:
    """
    Computes BM25 sparse keyword matching scores for all candidate activities.
    """
    query_tokens = tokenize(query_text)
    if not query_tokens:
        return {act.id: 0.0 for act in activities}

    # Document representations
    doc_tokens: Dict[str, List[str]] = {}
    doc_lengths: Dict[str, int] = {}
    for act in activities:
        doc_text = f"{act.activity_code} {act.name} {act.discipline} {act.wbs_name or ''} {act.location_scope or ''}"
        tokens = tokenize(doc_text)
        doc_tokens[act.id] = tokens
        doc_lengths[act.id] = len(tokens)

    n_docs = max(1, len(activities))
    avg_dl = sum(doc_lengths.values()) / n_docs if n_docs > 0 else 1.0

    # Calculate document frequency (DF) for each query term
    df: Dict[str, int] = {}
    for token in set(query_tokens):
        df[token] = sum(1 for tokens in doc_tokens.values() if token in tokens)

    # BM25 parameters
    k1 = 1.5
    b = 0.75

    scores: Dict[str, float] = {}
    for act in activities:
        tokens = doc_tokens[act.id]
        dl = doc_lengths[act.id]
        score = 0.0
        
        # Term frequencies
        tf_map: Dict[str, int] = {}
        for t in tokens:
            tf_map[t] = tf_map.get(t, 0) + 1

        for qt in query_tokens:
            if qt in tf_map:
                tf = tf_map[qt]
                # IDF calculation
                term_df = df.get(qt, 0)
                idf = math.log(1.0 + (n_docs - term_df + 0.5) / (term_df + 0.5))
                # Term score
                numerator = tf * (k1 + 1.0)
                denominator = tf + k1 * (1.0 - b + b * (dl / avg_dl))
                score += idf * (numerator / denominator)

        scores[act.id] = max(0.0, score)

    return scores


def compute_dense_scores(
    event_embedding: Optional[List[float]], activities: List[ScheduleActivity]
) -> Dict[str, float]:
    """Computes dense vector cosine similarity for all candidate activities."""
    scores: Dict[str, float] = {}
    for act in activities:
        scores[act.id] = cosine_similarity(event_embedding, act.embedding)
    return scores


def reciprocal_rank_fusion(
    sparse_scores: Dict[str, float],
    dense_scores: Dict[str, float],
    rrf_k: int = 60,
) -> Dict[str, float]:
    """
    Combines sparse (lexical) and dense (vector) rankings using Reciprocal Rank Fusion (RRF).
    
    RRF Score = 1 / (k + rank_sparse) + 1 / (k + rank_dense)
    """
    # Sort IDs by score descending to determine 1-indexed ranks
    sparse_ranked = sorted(sparse_scores.keys(), key=lambda x: sparse_scores[x], reverse=True)
    dense_ranked = sorted(dense_scores.keys(), key=lambda x: dense_scores[x], reverse=True)

    sparse_ranks = {act_id: rank + 1 for rank, act_id in enumerate(sparse_ranked)}
    dense_ranks = {act_id: rank + 1 for rank, act_id in enumerate(dense_ranked)}

    rrf_scores: Dict[str, float] = {}
    for act_id in sparse_scores.keys():
        r_s = sparse_ranks.get(act_id, len(sparse_scores))
        r_d = dense_ranks.get(act_id, len(dense_scores))
        score = (1.0 / (rrf_k + r_s)) + (1.0 / (rrf_k + r_d))
        rrf_scores[act_id] = score

    return rrf_scores


def hybrid_retrieve_candidates(
    event: ProgressEvent,
    activities: List[ScheduleActivity],
    top_k: int = 5,
) -> List[ScheduleActivity]:
    """
    Performs hybrid retrieval (BM25 sparse + dense vector cosine with RRF)
    over candidate activities for a given ProgressEvent.
    """
    if not activities:
        return []

    # Build comprehensive query string from event
    query_parts = [
        event.work_description,
        event.discipline,
        event.location_chainage or "",
        event.raw_text_snippet or "",
    ]
    query_text = " ".join(query_parts)

    # 1. Sparse BM25 retrieval
    sparse_scores = compute_bm25_sparse_scores(query_text, activities)

    # 2. Dense vector retrieval
    dense_scores = compute_dense_scores(event.embedding, activities)

    # 3. Reciprocal Rank Fusion
    rrf_scores = reciprocal_rank_fusion(sparse_scores, dense_scores)

    # 4. Rank activities by RRF score descending
    sorted_activities = sorted(activities, key=lambda a: rrf_scores.get(a.id, 0.0), reverse=True)

    return sorted_activities[:top_k]
