# Repository Intelligence Platform

A local/self-hosted platform that builds a persistent, evidence-backed graph model of a software repository so LLM coding agents can query structure instead of re-reading files.

This repository implements all architecture phases with working implementations where practical and stub/pluggable integrations where full backends are optional:

- Repository scanning with configurable ignore rules
- Tree-sitter parsing for Python, YAML, and HCL/Terraform
- Intermediate Pydantic model decoupled from storage
- Neo4j graph persistence with source locations, confidence, evidence, and batched writes
- Semantic resolution (Jedi for Python; SCIP/LSP/Joern stubs)
- Vector retrieval store (in-memory keyword fallback; Qdrant stub)
- Persistent investigation memory (SQLite via SQLAlchemy; PostgreSQL-ready)
- OpenTelemetry tracing instrumentation (optional)
- MCP server exposing graph-query tools
- CLI for indexing and querying the graph

## Quick start

1. Start the backing services:

```bash
docker compose up -d
```

2. Install the package (using `uv` or `pip`):

```bash
uv pip install -e .
# or
pip install -e .
```

3. Index one or more repositories:

```bash
repo-intel index /path/to/repo-a
repo-intel index /path/to/repo-b

# With semantic resolution (Jedi for Python)
repo-intel index /path/to/repo --semantic

# Refresh the graph after code changes (clears old repo data first)
repo-intel index /path/to/repo --clear
```

4. Query the graph:

```bash
repo-intel list-repos

repo-intel find-symbol --repo myrepo main
repo-intel get-callers  "myrepo:main:abc123:main.py:main"
repo-intel get-callees  "myrepo:main:abc123:main.py:main"
repo-intel trace        "myrepo:main:abc123:main.py:main"
repo-intel list-symbols --type function --repo myrepo
repo-intel list-resources --repo myrepo

# Crossplane queries
repo-intel find-xrd XExampleApp
repo-intel find-compositions XExampleApp
repo-intel composition-functions "<composition-id>"

# Explain how a file is implemented (absolute path auto-detected)
repo-intel explain /absolute/path/to/file.yaml
repo-intel explain /absolute/path/to/file.yaml --repo repo-name

# MCP server for LLM agents
python -m repo_intelligence.mcp_server
# or, using the installed console script
repo-intel-mcp
```

## Using the MCP server

The MCP server exposes the graph-query tools to LLM agents such as Devin.

1. Make sure Neo4j is running and at least one repository is indexed (see **Quick start** above).
2. Start the MCP server:
   ```bash
   uv run repo-intel-mcp
   # or, from an activated virtualenv:
   # repo-intel-mcp
   ```
3. Connect it to your agent. For Devin, the project-level config is already provided at `.devin/mcp_config.json`; reload the project and Devin will auto-discover the `repo-intel` tools.
4. Ask questions:
   - *"How is `/path/to/file.yaml` implemented?"* → `explain_file`
   - *"What calls `create_order` in `main.py`?"* → `find_symbol` + `trace_execution_flow`
   - *"Which XRD defines `XExampleApp`?"* → `find_xrd`
   - *"Which Compositions target `XExampleApp`?"* → `find_compositions`
   - *"What repositories are indexed?"* → `list_repositories`

If you need to change the Neo4j URI or other settings without committing them, add an override to `.devin/mcp_config.local.json` (gitignored).

## Development

Run tests:

```bash
pytest tests/
```

The synthetic repository in `synthetic_repo/` is used for manual CLI demonstrations and integration tests.

## Implemented scope

- Scanner with configurable ignore lists
- Python parser: classes, functions, methods, imports, calls, class inheritance
- YAML parser: Kubernetes object detection and Crossplane relationships (XRD, Composition)
- HCL/Terraform parser: resources and modules
- Intermediate model with source locations, evidence, and confidence
- Neo4j persistence with batching and indexes
- Basic queries: callers, callees, imports, importers, execution flow tracing
- Crossplane queries: `find-xrd`, `find-compositions`, `composition-functions`
- Semantic resolution: pluggable `SemanticResolver` architecture with a Jedi backend for Python; SCIP/LSP/Joern stubs
- Vector retrieval store: in-memory keyword store plus Qdrant stub
- Persistent investigation memory: SQLite via SQLAlchemy (PostgreSQL-ready)
- OpenTelemetry tracing instrumentation (optional)
- MCP server exposing graph-query tools to LLM agents
- CLI and automated tests

## Phase docs

- `docs/architecture.md`
- `docs/graph-model.md`
- `docs/indexing.md`
- `docs/parsers.md`
- `docs/semantic-resolution.md`
- `docs/mcp.md`
- `docs/mcp-vs-devin-tools.md`
