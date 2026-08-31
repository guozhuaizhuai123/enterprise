"""Lazy-loaded local embedding model, shared process-wide.

Loading the model is the expensive part (~100MB download on first run);
this module makes sure it only happens once regardless of how many
departments/documents call into it.
"""
import re
import threading

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import get_settings

settings = get_settings()

_lock = threading.Lock()
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vectors]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]


def tokenize(text: str) -> list[str]:
    """Same bigram-fallback tokenizer as the enterprise-kb-agent prototype:
    Chinese has no natural word boundaries, so ASCII words are kept whole
    and CJK runs are split into overlapping bigrams, which is good enough
    for BM25 without pulling in a full segmenter dependency."""
    text = re.sub(r"[^一-龥a-zA-Z0-9]", " ", text)
    tokens: list[str] = []
    for word in text.split():
        if re.match(r"^[a-zA-Z0-9]+$", word):
            tokens.append(word.lower())
        else:
            bigrams = [word[i : i + 2] for i in range(len(word) - 1)]
            tokens.extend(bigrams or [word])
    return tokens


def cosine_similarity_matrix(query_vec: list[float], matrix: np.ndarray) -> np.ndarray:
    if matrix.size == 0:
        return np.array([])
    q = np.asarray(query_vec)
    return matrix @ q  # vectors are already normalized at embed time
