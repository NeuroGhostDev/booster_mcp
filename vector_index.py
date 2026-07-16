import re
from collections.abc import Iterable
from typing import Any

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

_WORD_PATTERN = re.compile(r"[^\W_]+(?:_[^\W_]+)*", re.UNICODE)
_CAMEL_CASE_BOUNDARY = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


class VectorIndex:
    """Combines cosine similarity, BM25, and reciprocal-rank fusion."""

    def __init__(self, dim: int = 384):
        self.dim = dim
        self.base_index = faiss.IndexFlatIP(dim)
        self.index = faiss.IndexIDMap(self.base_index)
        self.meta: dict[int, dict[str, Any]] = {}
        self.file_ids: dict[str, list[int]] = {}
        self.next_id = 0
        self._lexical_documents: dict[int, list[str]] = {}
        self._bm25: BM25Okapi | None = None
        self._bm25_ids: list[int] = []
        self._bm25_dirty = True

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Keeps full identifiers and their snake_case/camelCase components."""
        tokens: list[str] = []
        for word in _WORD_PATTERN.findall(text):
            tokens.append(word.casefold())
            for camel_case_part in _CAMEL_CASE_BOUNDARY.split(word):
                for token in camel_case_part.split("_"):
                    if token:
                        tokens.append(token.casefold())
        return tokens

    def _normalize_vector(self, vector: Iterable[float]) -> np.ndarray:
        normalized = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        if normalized.shape[1] != self.dim:
            raise ValueError(
                f"Vector dimension {normalized.shape[1]} does not match index dimension {self.dim}."
            )
        faiss.normalize_L2(normalized)
        return normalized

    def _mark_lexical_index_dirty(self) -> None:
        self._bm25_dirty = True

    def _ensure_bm25(self) -> None:
        if not self._bm25_dirty:
            return

        self._bm25_ids = sorted(self._lexical_documents)
        if self._bm25_ids:
            corpus = [self._lexical_documents[doc_id]
                      for doc_id in self._bm25_ids]
            self._bm25 = BM25Okapi(corpus)
        else:
            self._bm25 = None
        self._bm25_dirty = False

    def _dense_candidates(self, vector: Iterable[float], limit: int) -> list[tuple[int, float]]:
        if self.index.ntotal == 0 or limit <= 0:
            return []

        scores, identifiers = self.index.search(
            self._normalize_vector(vector), min(limit, self.index.ntotal)
        )
        return [
            (int(identifier), float(score))
            for score, identifier in zip(scores[0], identifiers[0])
            if identifier != -1 and int(identifier) in self.meta
        ]

    def remove_file(self, file: str) -> None:
        ids_to_remove = self.file_ids.pop(file, [])
        if not ids_to_remove:
            return

        self.index.remove_ids(np.asarray(ids_to_remove, dtype=np.int64))
        for identifier in ids_to_remove:
            self.meta.pop(identifier, None)
            self._lexical_documents.pop(identifier, None)
        self._mark_lexical_index_dirty()

    def add(self, vector: Iterable[float], meta: dict[str, Any]) -> None:
        file = str(meta["file"])
        vec_id = self.next_id
        self.next_id += 1

        self.index.add_with_ids(
            self._normalize_vector(vector),
            np.asarray([vec_id], dtype=np.int64),
        )

        self.meta[vec_id] = meta
        self.file_ids.setdefault(file, []).append(vec_id)
        document = f"{meta.get('file', '')}\n{meta.get('chunk', '')}"
        self._lexical_documents[vec_id] = self._tokenize(document)
        self._mark_lexical_index_dirty()

    def search(self, vector: Iterable[float], k: int = 5) -> list[dict[str, Any]]:
        """Returns dense cosine-similarity results for backwards compatibility."""
        return [self.meta[identifier] for identifier, _ in self._dense_candidates(vector, k)]

    def hybrid_search(
        self,
        vector: Iterable[float],
        query: str,
        k: int = 5,
        candidate_k: int | None = None,
        rrf_constant: int = 60,
    ) -> list[dict[str, Any]]:
        """Fuses semantic and lexical candidates with reciprocal-rank fusion."""
        if k <= 0 or self.index.ntotal == 0:
            return []
        if rrf_constant <= 0:
            raise ValueError("rrf_constant must be greater than zero.")

        limit = candidate_k or max(k * 4, 20)
        fused: dict[int, dict[str, Any]] = {}

        def add_rank(identifier: int, source: str, rank: int, raw_score: float) -> None:
            entry = fused.setdefault(
                identifier,
                {
                    "score": 0.0,
                    "sources": set(),
                    "dense_rank": None,
                    "dense_score": None,
                    "lexical_rank": None,
                    "lexical_score": None,
                },
            )
            entry["score"] += 1 / (rrf_constant + rank)
            entry["sources"].add(source)
            entry[f"{source}_rank"] = rank
            entry[f"{source}_score"] = raw_score

        for rank, (identifier, score) in enumerate(self._dense_candidates(vector, limit), start=1):
            add_rank(identifier, "dense", rank, score)

        query_tokens = self._tokenize(query)
        if query_tokens:
            self._ensure_bm25()
            if self._bm25 is not None:
                lexical_scores = self._bm25.get_scores(query_tokens)
                for rank, position in enumerate(
                    np.argsort(-lexical_scores, kind="stable")[:limit], start=1
                ):
                    score = float(lexical_scores[position])
                    if score <= 0:
                        break
                    add_rank(self._bm25_ids[int(position)],
                             "lexical", rank, score)

        ranked = sorted(
            fused.items(),
            key=lambda item: (-item[1]["score"], item[0]),
        )
        results = []
        for identifier, details in ranked[:k]:
            result = dict(self.meta[identifier])
            result["retrieval"] = {
                "method": "hybrid_rrf",
                "score": round(details["score"], 8),
                "sources": sorted(details["sources"]),
                "dense_rank": details["dense_rank"],
                "dense_score": details["dense_score"],
                "lexical_rank": details["lexical_rank"],
                "lexical_score": details["lexical_score"],
            }
            results.append(result)
        return results
