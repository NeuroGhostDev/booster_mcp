import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

_WORD_PATTERN = re.compile(r"[^\W_]+(?:_[^\W_]+)*", re.UNICODE)
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


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
            corpus = [self._lexical_documents[doc_id] for doc_id in self._bm25_ids]
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
                    add_rank(self._bm25_ids[int(position)], "lexical", rank, score)

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

    def clone(self) -> "VectorIndex":
        """Клонирует FAISS/BM25 state для фоновой candidate generation."""
        cloned = VectorIndex(self.dim)
        cloned.index = faiss.clone_index(self.index)
        cloned.base_index = getattr(cloned.index, "index", cloned.index)
        cloned.meta = {identifier: dict(value) for identifier, value in self.meta.items()}
        cloned.file_ids = {
            file_name: list(identifiers) for file_name, identifiers in self.file_ids.items()
        }
        cloned.next_id = self.next_id
        cloned._lexical_documents = {
            identifier: list(tokens) for identifier, tokens in self._lexical_documents.items()
        }
        cloned._bm25 = None
        cloned._bm25_ids = list(self._bm25_ids)
        cloned._bm25_dirty = True
        return cloned

    def save(self, directory: str | Path, root: str | Path | None = None) -> None:
        """Persist the existing vector/lexical state without executable data."""
        target = Path(directory).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        repository_root = Path(root).expanduser().resolve() if root is not None else None

        def portable_path(value: Any) -> str:
            path = Path(str(value))
            if repository_root is not None and path.is_absolute():
                try:
                    return path.relative_to(repository_root).as_posix()
                except ValueError:
                    return str(path)
            return str(value)

        meta = {}
        for identifier, value in self.meta.items():
            item = dict(value)
            if "file" in item:
                item["file"] = portable_path(item["file"])
            meta[str(identifier)] = item
        faiss.write_index(self.index, str(target / "index.faiss"))
        payload = {
            "version": 1,
            "dim": self.dim,
            "next_id": self.next_id,
            "meta": meta,
            "file_ids": {
                portable_path(file_path): identifiers
                for file_path, identifiers in self.file_ids.items()
            },
            "lexical_documents": {
                str(identifier): tokens for identifier, tokens in self._lexical_documents.items()
            },
        }
        (target / "metadata.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def load(cls, directory: str | Path, root: str | Path | None = None) -> "VectorIndex":
        """Load JSON metadata and FAISS state produced by :meth:`save`."""
        target = Path(directory).expanduser().resolve()
        try:
            payload = json.loads((target / "metadata.json").read_text(encoding="utf-8"))
            loaded_index = faiss.read_index(str(target / "index.faiss"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError) as exc:
            raise ValueError("Invalid prebuilt vector index") from exc
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("Unsupported prebuilt vector index version")
        dim = payload.get("dim")
        if not isinstance(dim, int) or dim <= 0:
            raise ValueError("Invalid prebuilt vector index dimension")
        if loaded_index.d != dim:
            raise ValueError("Prebuilt vector index dimension mismatch")
        result = cls(dim=dim)
        result.index = loaded_index
        result.base_index = getattr(loaded_index, "index", loaded_index)
        raw_meta = payload.get("meta")
        raw_file_ids = payload.get("file_ids")
        raw_lexical = payload.get("lexical_documents")
        if (
            not isinstance(raw_meta, dict)
            or not isinstance(raw_file_ids, dict)
            or not isinstance(raw_lexical, dict)
        ):
            raise ValueError("Invalid prebuilt vector index metadata")
        repository_root = Path(root).expanduser().resolve() if root is not None else None

        def absolute_path(value: Any) -> str:
            path = Path(str(value))
            if repository_root is not None and not path.is_absolute():
                return str((repository_root / path).resolve())
            return str(path)

        result.meta = {}
        for identifier, value in raw_meta.items():
            if not isinstance(value, dict):
                raise ValueError("Invalid prebuilt vector metadata entry")
            item = dict(value)
            if "file" in item:
                item["file"] = absolute_path(item["file"])
            result.meta[int(identifier)] = item
        result.file_ids = {
            absolute_path(file_path): [int(identifier) for identifier in identifiers]
            for file_path, identifiers in raw_file_ids.items()
            if isinstance(identifiers, list)
        }
        result._lexical_documents = {
            int(identifier): [str(token) for token in tokens]
            for identifier, tokens in raw_lexical.items()
            if isinstance(tokens, list)
        }
        result.next_id = int(payload.get("next_id", max(result.meta, default=-1) + 1))
        result._bm25 = None
        result._bm25_ids = []
        result._bm25_dirty = True
        return result
