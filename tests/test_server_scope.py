from __future__ import annotations

from pathlib import Path

import pytest

import server
from server import _startup_repos


def test_workspace_bound_server_does_not_import_unrelated_registry_repositories(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    unrelated = tmp_path / "unrelated"

    scoped = _startup_repos([str(workspace)], [str(workspace), str(unrelated)])
    unbound = _startup_repos([], [str(workspace), str(unrelated)])

    assert scoped == [str(workspace.resolve())]
    assert unbound == [str(workspace.resolve()), str(unrelated.resolve())]


def test_search_does_not_return_silent_empty_results_while_indexing(monkeypatch) -> None:
    class EmptyIndexer:
        symbols = {}

        def stats(self) -> dict[str, int]:
            return {"files_indexed": 0, "vectors_in_faiss": 0}

    monkeypatch.setattr(server, "indexer", EmptyIndexer())
    monkeypatch.setattr(server, "_index_jobs", {"repo": {"status": "running"}})

    with pytest.raises(RuntimeError, match="Индекс ещё строится"):
        server._require_search_ready()
