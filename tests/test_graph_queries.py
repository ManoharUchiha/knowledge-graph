from unittest.mock import MagicMock
from repo_intelligence.graph.client import Neo4jClient
from repo_intelligence.graph.queries import GraphQueries


def test_find_symbol_builds_query():
    mock_client = MagicMock(spec=Neo4jClient)
    mock_client.execute_query.return_value = []
    queries = GraphQueries(mock_client)
    queries.find_symbol("main", repo="myrepo")

    args, _ = mock_client.execute_query.call_args
    query, params = args[0], args[1]
    assert params["name"] == "main"
    assert params["repo"] == "myrepo"


def test_get_callers_builds_query():
    mock_client = MagicMock(spec=Neo4jClient)
    mock_client.execute_query.return_value = [
        {"id": "caller", "name": "caller", "type": "function", "file_path": "f.py", "line": 1, "confidence": 0.95}
    ]
    queries = GraphQueries(mock_client)
    results = queries.get_callers("symbol:1")
    assert len(results) == 1
    assert results[0]["id"] == "caller"
