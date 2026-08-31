"""Hybrid retrieval: BM25 score + cosine similarity, both computed against
an already-built per-department index (app/kb/index_cache.py). Query time
only tokenizes + embeds the user's question — never the documents."""
from dataclasses import dataclass
from collections.abc import Sequence

import numpy as np
from sqlalchemy.orm import Session

from app.kb.embedding import cosine_similarity_matrix, embed_query, tokenize
from app.kb.index_cache import department_index_cache


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    text: str
    bm25_score: float
    cosine_score: float
    combined_score: float


def _normalize(scores: np.ndarray) -> np.ndarray:
    if scores.size == 0:
        return scores
    lo, hi = scores.min(), scores.max()
    if hi - lo < 1e-9:
        return np.zeros_like(scores)
    return (scores - lo) / (hi - lo)


def search(
    db: Session,
    *,
    department_id: str,
    query: str,
    top_k: int = 4,
    bm25_weight: float = 0.4,
    embedding_weight: float = 0.6,
    document_ids: frozenset[str] | None = None,
) -> list[RetrievedChunk]:
    idx = department_index_cache.get(db, department_id)
    if not idx.texts or document_ids == frozenset():
        return []

    candidate_indexes = np.arange(len(idx.texts))
    if document_ids is not None:
        candidate_indexes = np.array(
            [index for index, document_id in enumerate(idx.document_ids) if document_id in document_ids]
        )
    if candidate_indexes.size == 0:
        return []

    bm25_all = np.array(idx.bm25.get_scores(tokenize(query))) if idx.bm25 else np.zeros(len(idx.texts))
    bm25_raw = bm25_all[candidate_indexes]

    query_vec = embed_query(query)
    cosine_raw = cosine_similarity_matrix(query_vec, idx.vectors[candidate_indexes])
    if cosine_raw.size == 0:
        cosine_raw = np.zeros(candidate_indexes.size)

    combined = bm25_weight * _normalize(bm25_raw) + embedding_weight * _normalize(cosine_raw)
    ranked_positions = np.argsort(-combined)[:top_k]
    if document_ids is not None and candidate_indexes.size == 1:
        combined[0] = 1.0

    return [
        RetrievedChunk(
            chunk_id=idx.chunk_ids[candidate_indexes[position]],
            document_id=idx.document_ids[candidate_indexes[position]],
            text=idx.texts[candidate_indexes[position]],
            bm25_score=float(bm25_raw[position]),
            cosine_score=float(cosine_raw[position]),
            combined_score=float(combined[position]),
        )
        for position in ranked_positions
        if combined[position] > 0
    ]


def search_departments(
    db: Session,
    *,
    department_ids: Sequence[str],
    query: str,
    top_k: int = 4,
    document_ids: frozenset[str] | None = None,
) -> list[RetrievedChunk]:
    """Search each authorized department, then merge the strongest matches."""
    results = [
        chunk
        for department_id in department_ids
        for chunk in search(
            db, department_id=department_id, query=query, top_k=top_k, document_ids=document_ids
        )
    ]
    results.sort(key=lambda chunk: chunk.combined_score, reverse=True)
    return results[:top_k]
