import json
import subprocess
import sys
from pathlib import Path

from repository_lifecycle import RepositoryRegistry, RepositorySnapshotStore


def git(*arguments: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def test_repository_registry_survives_a_new_process_view(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    registry_root = tmp_path / "registry"

    first = RepositoryRegistry(registry_root)
    first.add(repo)
    first.add(repo)

    child = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, sys; "
                "from repository_lifecycle import RepositoryRegistry; "
                "print(json.dumps(RepositoryRegistry(sys.argv[1]).list_repos()))"
            ),
            str(registry_root),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(child.stdout) == [str(repo.resolve())]

    second = RepositoryRegistry(registry_root)
    assert second.list_repos() == [str(repo.resolve())]
    assert second.get(repo)["repository"] == str(repo.resolve())

    assert second.remove(repo) is True
    assert RepositoryRegistry(registry_root).list_repos() == []


def test_repository_registry_serializes_cross_process_updates(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    registry_root = tmp_path / "registry"
    RepositoryRegistry(registry_root).add(repo)

    code = (
        "import sys; "
        "from repository_lifecycle import RepositoryRegistry; "
        "RepositoryRegistry(sys.argv[1]).update(sys.argv[2], **{sys.argv[3]: sys.argv[4]})"
    )
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                code,
                str(registry_root),
                str(repo),
                f"worker_{index}",
                str(index),
            ],
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index in range(4)
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, (stdout, stderr)

    record = RepositoryRegistry(registry_root).get(repo)
    assert record is not None
    assert {record[f"worker_{index}"] for index in range(4)} == {"0", "1", "2", "3"}


def test_snapshot_history_is_immutable_and_commit_bound(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "source.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    artifacts = repo / ".agents" / "booster"
    artifacts.mkdir(parents=True)
    (artifacts / "repo_map.md").write_text("version one\n", encoding="utf-8")
    (artifacts / "code_city.html").write_text("<html>one</html>\n", encoding="utf-8")
    (artifacts / "scan_config.json").write_text("{}\n", encoding="utf-8")
    (artifacts / "scan_report.json").write_text(
        '{"generated_at_utc":"one","summary":{"files":1}}\n', encoding="utf-8"
    )

    git("init", cwd=repo)
    git("config", "user.email", "tests@example.com", cwd=repo)
    git("config", "user.name", "Booster Tests", cwd=repo)
    git("add", ".", cwd=repo)
    git("commit", "-m", "initial snapshot source", cwd=repo)
    commit = git("rev-parse", "HEAD", cwd=repo)

    store = RepositorySnapshotStore(repo)
    first = store.capture(task_id="task-1", reason="task_complete")
    first_map = Path(first["snapshot_dir"]) / "repo_map.md"

    (artifacts / "repo_map.md").write_text("version two\n", encoding="utf-8")
    (artifacts / "scan_report.json").write_text(
        '{"generated_at_utc":"two","summary":{"files":1}}\n', encoding="utf-8"
    )
    second = store.capture(task_id="task-2", reason="task_complete")

    assert first["commit"] == commit
    assert second["commit"] == commit
    assert first["snapshot_id"] != second["snapshot_id"]
    assert first_map.read_text(encoding="utf-8") == "version one\n"
    assert (Path(second["snapshot_dir"]) / "repo_map.md").read_text(
        encoding="utf-8"
    ) == "version two\n"
    (artifacts / "scan_report.json").write_text(
        '{"generated_at_utc":"three","summary":{"files":1}}\n', encoding="utf-8"
    )
    third = store.capture(task_id="task-3", reason="task_complete")
    assert third["snapshot_id"] == second["snapshot_id"]
    assert store.latest()["snapshot_id"] == second["snapshot_id"]
    assert {item["snapshot_id"] for item in store.list_snapshots()} == {
        first["snapshot_id"],
        second["snapshot_id"],
    }

    metadata = json.loads(
        (Path(first["snapshot_dir"]) / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["previous_snapshots_preserved"] is True
