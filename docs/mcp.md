# MCP Server

The platform exposes repository intelligence through an MCP server using the official Python SDK. It works for **any indexed repository**, not just Crossplane.

## Running the server

```bash
python -m repo_intelligence.mcp_server
```

Or, after installing the package, use the installed console script (run through `uv` or from an activated virtualenv):

```bash
uv run repo-intel-mcp
```

## Team deployment

The project-level MCP config lives at `.devin/mcp_config.json` and is committed to version control, so any teammate who opens this repository in Devin can run the `repo-intel` MCP server without manual setup.

Prerequisites:

1. `uv` (or `pip`) and Python 3.11+
2. Neo4j running — start it with the bundled Docker Compose:
   ```bash
   docker compose up -d
   ```
3. The package installed in editable mode:
   ```bash
   uv pip install -e .
   # or pip install -e .
   ```
4. One or more repositories indexed in Neo4j:
   ```bash
   repo-intel index /path/to/repo-a
   repo-intel index /path/to/repo-b
   ```

Once these steps are done, Devin loads `repo-intel` automatically from `.devin/mcp_config.json`. To override environment variables (for example, a different Neo4J URI) without committing secrets, add them to the gitignored `.devin/mcp_config.local.json`:

```json
{
  "mcpServers": {
    "repo-intel": {
      "env": {
        "NEO4J_URI": "bolt://my-neo4j-host:7687"
      }
    }
  }
}
```

## Connecting to Devin

A project-level MCP config has been added at `.devin/mcp_config.json`.

Restart Devin or reload the project so the server is picked up. Once loaded, Devin can call the `repo-intel` tools directly.

You can also add it manually with the Devin CLI:

```bash
devin mcp add -s project -e NEO4J_URI=bolt://localhost:7687 repo-intel -- \
  ./.venv/bin/python \
  -m repo_intelligence.mcp_server
```

## Available tools

| Tool | Purpose |
|------|---------|
| `explain_file` | Explain how a file is implemented (symbols, Crossplane chain, Python refs). Accepts absolute or relative paths; `repo` is optional. |
| `find_symbol` | Locate a symbol/function/class/resource by name across all indexed repos. |
| `find_xrd` | Find XRDs that define a Crossplane XR kind. |
| `find_compositions` | Find Compositions that target a Crossplane XR kind. |
| `trace_execution_flow` | Follow call chains from a symbol ID. |
| `list_repositories` | List every repository currently indexed in Neo4j. |

All tools return structured JSON that the LLM can use to request exact source evidence.

## On-demand indexing (self-healing graph)

`explain_file` keeps the graph current on every call so you can validate brand-new
or freshly edited files without re-running a full `repo-intel index`:

- **Missing file** — if the file exists on disk inside an indexed repository but is
  absent from the graph, it is parsed and added, then explained. The response
  includes `"on_demand_indexing": { "action": "created", ... }`.
- **Changed file** — each file node stores a `content_hash`. When the file on disk
  differs, its previously indexed symbols are removed and it is re-parsed. The
  response includes `"on_demand_indexing": { "action": "refreshed", ... }`.
- **Unchanged file** — when the hash matches, the graph is left untouched and the
  response includes `"index_status": "up_to_date"`.

Safeguards: only files inside an already-indexed `Repository.root_path` are
touched, paths are resolved with `realpath` to prevent traversal/symlink escapes,
ignored directories and unsupported/oversized files are skipped, and shared
placeholder nodes (e.g. `xrdtype:*`, `fn:*`) are preserved during a refresh.

Auto-indexing is on by default. Disable it globally with
`REPO_INTEL_AUTO_INDEX_MISSING=false`, or per call with `index_if_missing=false`.
Relative paths require the `repo` argument so the correct repository is selected.

## Example Devin prompt

```text
How is /path/to/repository/example-resource.yaml implemented?
```

With the `.devin/rules/use-repo-intel-mcp.md` rule in place, Devin should call `repo-intel` → `explain_file` and return the structured explanation.
