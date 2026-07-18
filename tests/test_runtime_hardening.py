from typing import Any

import pytest

from indexer import RepoIndexer


def test_full_index_delegates_to_single_repo_indexing() -> None:
    indexer = RepoIndexer.__new__(RepoIndexer)
    indexer.repos = ["repo-a", "repo-b"]
    calls: list[str] = []

    def fake_index_repo(repo: str) -> Any:
        calls.append(repo)
        return None

    indexer.index_repo = fake_index_repo

    RepoIndexer.full_index(indexer)

    assert calls == ["repo-a", "repo-b"]


def test_code_city_port_zero_logs_actual_bound_port(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import city_server

    class FakeHTTPServer:
        def __init__(self, server_address: tuple[str, int], handler: Any):
            self.requested_address = server_address
            self.handler = handler
            self.server_address = ("0.0.0.0", 49152)

        def serve_forever(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    monkeypatch.setattr(city_server, "HTTPServer", FakeHTTPServer)

    city_server.run_server(port=0, open_browser=False)

    captured = capsys.readouterr()
    assert "http://localhost:49152" in captured.err
    assert "http://localhost:0" not in captured.err
