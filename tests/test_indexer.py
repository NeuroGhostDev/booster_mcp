from __future__ import annotations

from pathlib import Path

from indexer import RepoIndexer


def test_index_repo_removes_files_deleted_since_previous_scan(tmp_path: Path) -> None:
    old_file = tmp_path / "old.py"
    new_file = tmp_path / "new.py"
    old_file.write_text("def old():\n    return 1\n", encoding="utf-8")
    new_file.write_text("def new():\n    return 2\n", encoding="utf-8")

    indexer = RepoIndexer([])
    old_key = str(old_file.resolve())
    indexer.symbols[old_key] = [{"name": "old", "file": old_key}]

    def fake_index_file(path: Path) -> None:
        key = str(Path(path).resolve())
        indexer.symbols[key] = [{"name": Path(path).stem, "file": key}]

    indexer.index_file = fake_index_file  # type: ignore[method-assign]
    old_file.unlink()

    result = indexer.index_repo(str(tmp_path))

    assert len(result.files) == 1
    assert old_key not in indexer.symbols
    assert str(new_file.resolve()) in indexer.symbols
