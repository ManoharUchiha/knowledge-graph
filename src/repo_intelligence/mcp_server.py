"""MCP server exposing repository-intelligence tools to LLM agents.

Run with:

    python -m repo_intelligence.mcp_server

or configure as an MCP stdio server in a client.
"""
from __future__ import annotations
import json
import os
from typing import Any, Optional

from repo_intelligence.graph.client import Neo4jClient
from repo_intelligence.graph.queries import GraphQueries
from repo_intelligence.indexer import FileIndexer

try:
    from mcp.server.fastmcp import FastMCP
    HAS_MCP = True
except ImportError:  # pragma: no cover
    HAS_MCP = False


def _get_queries() -> GraphQueries:
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    return GraphQueries(Neo4jClient(neo4j_uri))


def _json_text(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _auto_index_enabled() -> bool:
    return os.environ.get("REPO_INTEL_AUTO_INDEX_MISSING", "true").lower() in ("1", "true", "yes")


def _explain_file(
    file_path: str,
    repo: Optional[str],
    index_if_missing: bool,
    client: Optional[Neo4jClient] = None,
) -> dict:
    graph_client = client or Neo4jClient(os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    queries = GraphQueries(graph_client)

    if not index_if_missing or not _auto_index_enabled():
        return queries.explain_file(file_path, repo=repo)

    # Keep the graph current before answering: this indexes files missing from
    # the graph and refreshes files whose on-disk content has changed.
    indexing = FileIndexer(graph_client).index_file(file_path, repo=repo)
    result = queries.explain_file(file_path, repo=repo)

    if "error" in result:
        # Nothing useful in the graph; surface the more descriptive indexing
        # error when indexing also failed (e.g. unsupported or missing file).
        return indexing if "error" in indexing else result

    if indexing.get("indexed"):
        result["on_demand_indexing"] = indexing
    elif indexing.get("up_to_date"):
        result["index_status"] = "up_to_date"
    elif "error" in indexing:
        result["index_warning"] = indexing
    return result


def create_server() -> Any:
    if not HAS_MCP:
        raise RuntimeError("MCP SDK is not installed")

    mcp = FastMCP(
        "repo-intel",
        instructions=(
            "Repository intelligence graph query tools backed by Neo4j. "
            "Use these tools FIRST for any question about repository structure, "
            "file implementation, symbol definitions, Crossplane resources, or "
            "execution flow. They work for any indexed repository, not only "
            "Crossplane."
        ),
    )

    @mcp.tool()
    async def explain_file(
        file_path: str,
        repo: Optional[str] = None,
        index_if_missing: bool = True,
    ) -> str:
        """Explain how a repository file is implemented.

        PREFERRED TOOL for questions about a specific repository file path,
        resource usage, or how a resource is wired to its definitions.
        Works for any indexed repository (Crossplane, Terraform, Python, etc.).
        The file_path may be absolute or relative; repo is optional and may be a
        name or directory fragment.
        """
        return _json_text(_explain_file(file_path, repo, index_if_missing))

    @mcp.tool()
    async def find_symbol(
        name: str,
        repo: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> str:
        """Find symbols (functions/classes/variables/resources) by name in the graph.

        PREFERRED TOOL when the user asks for a symbol, function, class,
        resource, or identifier by name instead of a file path. Works for any
        indexed repository.
        """
        return _json_text(_get_queries().find_symbol(name, repo=repo, branch=branch))

    @mcp.tool()
    async def find_xrd(
        kind: str,
        repo: Optional[str] = None,
    ) -> str:
        """Find CompositeResourceDefinitions (Crossplane XRDs) that define the
        given XR kind.

        PREFERRED TOOL for Crossplane XRD lookups by kind (e.g. XExampleApp).
        """
        return _json_text(_get_queries().find_xrd_for_kind(kind, repo=repo))

    @mcp.tool()
    async def find_compositions(
        kind: str,
        repo: Optional[str] = None,
    ) -> str:
        """Find Crossplane Compositions that target the given XR kind.

        PREFERRED TOOL for Crossplane Composition lookups by XR kind.
        """
        return _json_text(_get_queries().find_compositions_for_kind(kind, repo=repo))

    @mcp.tool()
    async def trace_execution_flow(
        symbol_id: str,
        depth: int = 10,
    ) -> str:
        """Trace call graph forward from a starting symbol ID.

        PREFERRED TOOL for "what calls this" or execution-flow questions.
        Use a symbol id returned by explain_file or find_symbol.
        """
        return _json_text(_get_queries().trace_execution_flow(symbol_id, depth=depth))

    @mcp.tool()
    async def list_repositories() -> str:
        """List all repositories currently indexed in the graph."""
        return _json_text(_get_queries().list_repositories())

    return mcp


def main() -> None:
    mcp = create_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
