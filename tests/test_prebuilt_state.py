from __future__ import annotations

from pathlib import Path

from indexer import RepoIndexer
from vector_index import VectorIndex


def test_vector_index_roundtrip_is_json_faiss_only(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text("def service():\n", encoding="utf-8")
    index = VectorIndex(dim=2)
    index.add([1, 0], {"file": str(source), "chunk": "service"})
    bundle = tmp_path / "bundle"

    index.save(bundle, root=tmp_path)
    loaded = VectorIndex.load(bundle, root=tmp_path)

    assert loaded.file_ids == {str(source.resolve()): [0]}
    assert loaded.meta[0]["file"] == str(source.resolve())
    assert loaded.hybrid_search([1, 0], "service", k=1)[0]["file"] == str(source.resolve())


def test_repo_indexer_loads_prebuilt_state_into_same_runtime(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text("def service():\n", encoding="utf-8")
    indexer = RepoIndexer([])
    indexer.vector = VectorIndex(dim=2)
    indexer.vector.add([1, 0], {"file": str(source), "chunk": "service"})
    indexer.symbols = {
        str(source.resolve()): [{"name": "service", "file": str(source.resolve()), "start": 0}]
    }
    indexer.graphs.add_call(str(source.resolve()), "service", "repository")
    indexer.graphs.add_import(str(source.resolve()), "repository")
    indexer.generation_id = "prepared-generation"
    indexer.generation_metadata = {
        "generation_id": "prepared-generation",
        "repository": str(tmp_path.resolve()),
        "ready": True,
        "source_manifest": {"service.py": {"size_bytes": 20}},
    }

    bundle = tmp_path / "bundle"
    indexer.save_state(bundle, tmp_path)
    loaded = RepoIndexer([])
    health = loaded.load_state(bundle, tmp_path)

    assert health["generation_id"] == "prepared-generation"
    assert loaded.find_symbols("service")[0]["file"] == str(source.resolve())
    assert loaded.graphs.calls("service") == ["repository"]
    assert loaded.graphs.imports(str(source.resolve())) == ["repository"]
    assert list(loaded.vector.file_ids) == [str(source.resolve())]
