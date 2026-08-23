from __future__ import annotations

import http.client
import json
from pathlib import Path
from threading import Thread
from urllib.parse import quote, urlsplit

import city_server
from city_server import _code_city_path
from indexer import RepoIndexer


def test_code_city_uses_canonical_booster_artifact_directory(tmp_path: Path) -> None:
    assert _code_city_path(tmp_path) == (
        tmp_path.resolve() / ".agents" / "booster" / "code_city.html"
    )


def test_code_city_api_serves_registered_artifact(tmp_path: Path) -> None:
    artifact = _code_city_path(tmp_path)
    artifact.parent.mkdir(parents=True)
    artifact.write_text("<html>city</html>", encoding="utf-8")

    indexer = RepoIndexer([])
    indexer.repos[:] = [str(tmp_path.resolve())]
    city_server.set_indexer(indexer)
    httpd = city_server.HTTPServer(("127.0.0.1", 0), city_server.CodeCityHandler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1])
    try:
        encoded_repo = quote(str(tmp_path.resolve()), safe="")
        connection.request("GET", f"/api/code_city?repo={encoded_repo}")
        api_response = connection.getresponse()
        payload = json.loads(api_response.read().decode("utf-8"))
        assert api_response.status == 200
        assert payload["exists"] is True

        path = urlsplit(payload["url"]).path + "?" + urlsplit(payload["url"]).query
        connection.request("GET", path)
        city_response = connection.getresponse()
        assert city_response.status == 200
        assert city_response.read().decode("utf-8") == "<html>city</html>"
    finally:
        connection.close()
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
