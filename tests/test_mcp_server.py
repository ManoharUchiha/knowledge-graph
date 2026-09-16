from unittest.mock import MagicMock, patch

import pytest
from repo_intelligence.mcp_server import _explain_file, create_server


pytest.importorskip("mcp")


def test_mcp_server_has_expected_tools():
    server = create_server()
    names = set(server._tool_manager._tools.keys())
    assert "explain_file" in names
    assert "find_symbol" in names
    assert "find_xrd" in names
    assert "find_compositions" in names
    assert "trace_execution_flow" in names


def test_explain_file_indexes_a_missing_file_then_explains():
    explained = {"file": {"file_name": "xrd.yaml"}}

    with patch("repo_intelligence.mcp_server._auto_index_enabled", return_value=True), patch(
        "repo_intelligence.mcp_server.GraphQueries"
    ) as queries_class, patch("repo_intelligence.mcp_server.FileIndexer") as indexer_class:
        queries_class.return_value.explain_file.return_value = explained
        indexer_class.return_value.index_file.return_value = {
            "indexed": True,
            "action": "created",
            "repo": "test-repo",
            "file_path": "xrd.yaml",
        }
        result = _explain_file("/repo/xrd.yaml", None, True, client=MagicMock())

    assert result["file"] == explained["file"]
    assert result["on_demand_indexing"]["action"] == "created"
    queries_class.return_value.explain_file.assert_called_once_with("/repo/xrd.yaml", repo=None)
    indexer_class.return_value.index_file.assert_called_once_with("/repo/xrd.yaml", repo=None)


def test_explain_file_marks_up_to_date_when_unchanged():
    explained = {"file": {"file_name": "xrd.yaml"}}

    with patch("repo_intelligence.mcp_server._auto_index_enabled", return_value=True), patch(
        "repo_intelligence.mcp_server.GraphQueries"
    ) as queries_class, patch("repo_intelligence.mcp_server.FileIndexer") as indexer_class:
        queries_class.return_value.explain_file.return_value = explained
        indexer_class.return_value.index_file.return_value = {"indexed": False, "up_to_date": True}
        result = _explain_file("/repo/xrd.yaml", None, True, client=MagicMock())

    assert result["index_status"] == "up_to_date"
    assert "on_demand_indexing" not in result


def test_explain_file_returns_indexing_error_when_graph_empty():
    missing = {"error": "File not indexed", "error_code": "FILE_NOT_INDEXED"}
    indexing_error = {"error": "outside repo", "error_code": "FILE_OUTSIDE_REPOSITORY"}

    with patch("repo_intelligence.mcp_server._auto_index_enabled", return_value=True), patch(
        "repo_intelligence.mcp_server.GraphQueries"
    ) as queries_class, patch("repo_intelligence.mcp_server.FileIndexer") as indexer_class:
        queries_class.return_value.explain_file.return_value = missing
        indexer_class.return_value.index_file.return_value = indexing_error
        result = _explain_file("/repo/xrd.yaml", None, True, client=MagicMock())

    assert result == indexing_error


def test_explain_file_does_not_index_when_disabled():
    missing = {"error": "File not indexed", "error_code": "FILE_NOT_INDEXED"}

    with patch("repo_intelligence.mcp_server.GraphQueries") as queries_class, patch(
        "repo_intelligence.mcp_server.FileIndexer"
    ) as indexer_class:
        queries_class.return_value.explain_file.return_value = missing
        result = _explain_file("/repo/xrd.yaml", None, False, client=MagicMock())

    assert result == missing
    indexer_class.assert_not_called()
