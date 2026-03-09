from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path
from visualizer import CodeCityVisualizer

class RepoWatcher(FileSystemEventHandler):
    def __init__(self, indexer):
        self.indexer = indexer
        self.visualizer = CodeCityVisualizer(indexer)
        self._regenerate_city = False

    def on_modified(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.exists():
            self.indexer.index_file(path)
            self._regenerate_city = True

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.exists():
            self.indexer.index_file(path)
            self._regenerate_city = True

    def on_deleted(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        self.indexer.vector.remove_file(str(path))
        self.indexer.graphs.clear_file(str(path))
        if str(path) in self.indexer.symbols:
            del self.indexer.symbols[str(path)]
        self._regenerate_city = True

    def on_any_event(self, event):
        # Перегенерируем Code City после серии изменений
        if self._regenerate_city and hasattr(self.indexer, 'repos') and self.indexer.repos:
            try:
                repo = self.indexer.repos[0]  # Берём первый репозиторий
                city_output = str(Path(repo) / "code_city.html")
                self.visualizer.generate_visualization(repo, city_output)
                self._regenerate_city = False
            except Exception:
                pass  # Игнорируем ошибки при фоновой генерации

def start_watch(indexer, repos):
    observer = Observer()
    watcher = RepoWatcher(indexer)
    for repo in repos:
        if Path(repo).exists():
            observer.schedule(watcher, repo, recursive=True)
    observer.start()
