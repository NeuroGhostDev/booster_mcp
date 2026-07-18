from pathlib import Path
from typing import Any, Iterable, cast

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from repository_scanner import IgnoreRules, ScanConfig
from visualizer import CodeCityVisualizer


class RepoWatcher(FileSystemEventHandler):
    def __init__(self, indexer: Any, repos: Iterable[str]):
        self.indexer = indexer
        self.visualizer = CodeCityVisualizer(indexer)
        self._regenerate_city = False
        self.repo_rules: dict[Path, IgnoreRules] = {}
        for repo in repos:
            repo_path = Path(repo).expanduser().resolve()
            if repo_path.exists():
                config = ScanConfig.load(repo_path)
                self.repo_rules[repo_path] = IgnoreRules.from_repository(
                    repo_path, config)

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
            self.indexer.index_file(path)
            self._regenerate_city = True

    def on_created(self, event: Any) -> None:
        if event.is_directory:
            return
        path = Path(str(event.src_path))
        if path.exists() and self._should_index(path):
            self.indexer.index_file(path)
            self._regenerate_city = True

    def on_deleted(self, event: Any) -> None:
        if event.is_directory:
            return
        path = Path(str(event.src_path))
        if self._repo_for_path(path) is None:
            return
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
                self.visualizer.generate_visualization(repo, city_output)
                self._regenerate_city = False
            except Exception:
                pass  # Игнорируем ошибки при фоновой генерации


def start_watch(indexer: Any, repos: Iterable[str]) -> None:
    observer = Observer()
    repo_list = list(repos)
    watcher = RepoWatcher(indexer, repo_list)
    for repo in repo_list:
        if Path(repo).exists():
            observer.schedule(watcher, repo, recursive=True)
    observer.start()
