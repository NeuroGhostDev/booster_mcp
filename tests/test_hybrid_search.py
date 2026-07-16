from vector_index import VectorIndex


def build_index() -> VectorIndex:
    index = VectorIndex(dim=2)
    index.add(
        [1, 0],
        {
            "file": "auth.py",
            "chunk": "def validateAccessToken(token):\n    return token",
        },
    )
    index.add(
        [0, 1],
        {
            "file": "billing.py",
            "chunk": "def create_invoice():\n    return None",
        },
    )
    index.add(
        [0, 0.9],
        {
            "file": "settings.py",
            "chunk": "def load_settings():\n    return {}",
        },
    )
    index.add(
        [0.2, 0.1],
        {
            "file": "worker.py",
            "chunk": "def run_worker():\n    return None",
        },
    )
    return index


def test_hybrid_search_matches_camel_case_identifier_from_snake_case_query():
    index = build_index()

    results = index.hybrid_search([0, 1], "validate_access_token", k=3)

    assert results[0]["file"] == "auth.py"
    assert results[0]["retrieval"]["method"] == "hybrid_rrf"
    assert "lexical" in results[0]["retrieval"]["sources"]


def test_hybrid_search_removes_deleted_file_from_dense_and_lexical_indexes():
    index = build_index()
    index.remove_file("auth.py")

    results = index.hybrid_search([0, 1], "validate access token", k=3)

    assert all(result["file"] != "auth.py" for result in results)
    assert index.index.ntotal == 3


def test_dense_search_keeps_its_existing_result_shape():
    index = build_index()

    results = index.search([0, 1], k=1)

    assert results == [
        {
            "file": "billing.py",
            "chunk": "def create_invoice():\n    return None",
        }
    ]
