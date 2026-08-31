"""Per-department in-memory index cache (PRD §5.2).

Documents are chunked + embedded exactly once, at write time, by the
document service (see app/kb/service.py), and persisted to the
`document_chunks` table. This module is the read-side: it loads each
department's chunks into a small in-process cache (BM25 corpus + a numpy
matrix of already-computed embeddings) once, and keeps it updated
incrementally on writes. Query time never re-tokenizes or re-embeds
document content — only the user's question gets embedded, and it's
matched against vectors that were already sitting in memory.
"""
import threading

import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

from app.models import DocumentChunk


class _DepartmentIndex:
    def __init__(self) -> None:
        self.chunk_ids: list[str] = []
        self.document_ids: list[str] = []
        self.texts: list[str] = []
        self.tokens: list[list[str]] = []
        self.vectors: np.ndarray = np.zeros((0, 0))
        self.bm25: BM25Okapi | None = None

    def rebuild_bm25(self) -> None:
        self.bm25 = BM25Okapi(self.tokens) if self.tokens else None


class DepartmentIndexCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._indexes: dict[str, _DepartmentIndex] = {}

    def _load_from_db(self, db: Session, department_id: str) -> _DepartmentIndex:
        rows = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.department_id == department_id)
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
            .all()
        )
        idx = _DepartmentIndex()
        for row in rows:
            idx.chunk_ids.append(row.id)
            idx.document_ids.append(row.document_id)
            idx.texts.append(row.chunk_text)
            idx.tokens.append(row.tokens)
        idx.vectors = np.array([row.embedding for row in rows]) if rows else np.zeros((0, 0))
        idx.rebuild_bm25()
        return idx

    def get(self, db: Session, department_id: str) -> _DepartmentIndex:
        with self._lock:
            if department_id not in self._indexes:
                self._indexes[department_id] = self._load_from_db(db, department_id)
            return self._indexes[department_id]

    def invalidate(self, department_id: str) -> None:
        """Drop the cached index so the next get() reloads from DB.
        Called after any write to that department's documents — only that
        department's cache is dropped, never the whole cache."""
        with self._lock:
            self._indexes.pop(department_id, None)


department_index_cache = DepartmentIndexCache()
