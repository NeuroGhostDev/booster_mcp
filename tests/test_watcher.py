from pathlib import Path
from types import SimpleNamespace

from watcher import RepoWatcher


class FakeIndexer:
    def __init__(self) -> None:
        self.indexed: list[Path] = []

    def index_file(self, path: Path) -> None:
        self.indexed.append(path)


def file_event(path: Path) -> SimpleNamespace:
    return SimpleNamespace(is_directory=False, src_path=str(path))


def test_watcher_respects_repository_scanner_ignore_rules(tmp_path: Path):
    source_file = tmp_path / "src" / "app.py"
    ignored_file = tmp_path / ".venv" / "Lib" / "site-packages" / "pkg.py"
    source_file.parent.mkdir(parents=True)
    ignored_file.parent.mkdir(parents=True)
    source_file.write_text("def app():\n    return True\n", encoding="utf-8")
    ignored_file.write_text(
        "def dependency():\n    return True\n", encoding="utf-8")

    indexer = FakeIndexer()
    watcher = RepoWatcher(indexer, [str(tmp_path)])

    watcher.on_modified(file_event(ignored_file))
    watcher.on_modified(file_event(source_file))

    assert indexer.indexed == [source_file]
