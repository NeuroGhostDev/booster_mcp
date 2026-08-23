import logging
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Iterable, cast

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from repository_scanner import IgnoreRules, ScanConfig
from visualizer import CodeCityVisualizer

logger = logging.getLogger(__name__)


class RepoWatcher(FileSystemEventHandler):
    def __init__(self, indexer: Any, repos: Iterable[str]):
        self.indexer = indexer
        self.visualizer = CodeCityVisualizer(indexer)
        self._regenerate_city = False
        self.repo_rules: dict[Path, IgnoreRules] = {}
        self._scheduled_repos: set[Path] = set()
        for repo in repos:
            self.add_repository(repo)

    def add_repository(self, repo: str | Path) -> Path | None:
        repo_path = Path(repo).expanduser().resolve()
        if not repo_path.exists() or repo_path in self.repo_rules:
            return repo_path if repo_path in self.repo_rules else None
        config = ScanConfig.load(repo_path)
        self.repo_rules[repo_path] = IgnoreRules.from_repository(repo_path, config)
        return repo_path

    def schedule_repository(self, observer: Observer, repo: str | Path) -> None:
        repo_path = self.add_repository(repo)
        if repo_path is not None and repo_path not in self._scheduled_repos:
            observer.schedule(self, str(repo_path), recursive=True)
            self._scheduled_repos.add(repo_path)

    def _repo_for_path(self, path: Path) -> Path | None:
        resolved = path.expanduser().resolve()
        for repo_path in self.repo_rules:
            try:
                resolved.relative_to(repo_path)
                return repo_path
            except ValueError:
                continue
        return None

    def _should_index(self, path: Path) -> bool:
        repo_path = self._repo_for_path(path)
        if repo_path is None:
            return False

        relative = path.resolve().relative_to(repo_path).as_posix()
        rules = self.repo_rules[repo_path]
        parts = Path(relative).parts
        parent_parts = parts[:-1]
        for index, part in enumerate(parent_parts):
            partial = "/".join(parts[: index + 1])
            if rules.ignores_directory(part, partial):
                return False

        return not rules.ignores_file(path.name, relative)

    def on_modified(self, event: Any) -> None:
        if event.is_directory:
            return
        path = Path(str(event.src_path))
        if path.exists() and self._should_index(path):
            on_change = getattr(self.indexer, "on_repository_change", None)
            if callable(on_change):
                on_change(str(self._repo_for_path(path)))
                return
            self.indexer.index_file(path)
            self._regenerate_city = True

    def on_created(self, event: Any) -> None:
        if event.is_directory:
            return
        path = Path(str(event.src_path))
        if path.exists() and self._should_index(path):
            on_change = getattr(self.indexer, "on_repository_change", None)
            if callable(on_change):
                on_change(str(self._repo_for_path(path)))
                return
            self.indexer.index_file(path)
            self._regenerate_city = True

    def on_deleted(self, event: Any) -> None:
        if event.is_directory:
            return
        path = Path(str(event.src_path))
        if self._repo_for_path(path) is None:
            return
        on_change = getattr(self.indexer, "on_repository_change", None)
        if callable(on_change):
            on_change(str(self._repo_for_path(path)))
            return
        remove_file = getattr(self.indexer, "remove_file", None)
        if callable(remove_file):
            remove_file(path)
        else:
            self.indexer.vector.remove_file(str(path))
            self.indexer.graphs.clear_file(str(path))
            if str(path) in self.indexer.symbols:
                del self.indexer.symbols[str(path)]
        self._regenerate_city = True

    def on_any_event(self, event: Any) -> None:
        # Перегенерируем Code City после серии изменений
        repos = cast(list[str], getattr(self.indexer, "repos", []))
        if self._regenerate_city and repos:
            try:
                repo = repos[0]  # Берём первый репозиторий
                city_output = str(Path(repo) / "code_city.html")
                lock = getattr(self.indexer, "operation_lock", nullcontext())
                with lock:
                    self.visualizer.generate_visualization(repo, city_output)
                self._regenerate_city = False
            except Exception:
                logger.exception("Code City background regeneration failed")


def start_watch(indexer: Any, repos: Iterable[str]) -> tuple[Observer, RepoWatcher]:
    observer = Observer()
    watcher = RepoWatcher(indexer, [])
    for repo in repos:
        watcher.schedule_repository(observer, repo)
    observer.start()
    return observer, watcher
