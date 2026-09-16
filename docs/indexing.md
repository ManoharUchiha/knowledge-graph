# Indexing

## Pipeline

1. **Git metadata** — `GitRepository` reads the current branch and commit.
2. **Scan** — `RepositoryScanner` walks the repository, skipping configured directories and binary files, and assigns languages by extension.
3. **Parse** — `ParserFactory` dispatches each file to the appropriate Tree-sitter parser.
4. **Resolve** — `resolve_relationships` maps module-qualified references such as `module:services.order.create_order` to actual file symbols when the source file exists in the repository.
5. **Persist** — `GraphBuilder` writes the model into Neo4j using `MERGE` to keep repeated indexing idempotent for the same (repo, branch, commit) snapshot.

## Performance

The graph builder batches nodes and relationships (default batch size 500) and runs a small set of setup indexes/constraints before writing:

- Unique constraint on `:Symbol.id`
- Indexes on `(repo, branch, commit)`, `kind`, `(type, name)`, and `Repository` snapshot fields.

This reduces the indexing time for large repositories from many minutes to a few seconds.

## Idempotency

`MERGE` is used for every symbol and relationship keyed by the full scoped id (`repo:branch:commit:file_path:qualified_name`). Re-indexing the same commit updates existing nodes and relationships in place.

## Git awareness

Every node and relationship carries:

- `repo` — repository name (derived from the top-level directory name)
- `branch`
- `commit`
- `file_path` and line numbers pointing back to source

If a directory is not a Git repository, the values default to `unknown`.

## Updating Neo4j with the latest code

The graph is a snapshot of the last indexed state. To refresh it:

```bash
# Fast re-index: updates existing nodes for the current commit, leaves older commits untouched.
repo-intel index /path/to/repo

# Clean re-index: removes all data for that repository name first, then writes a fresh snapshot.
repo-intel index /path/to/repo --clear

# With semantic resolution for Python
repo-intel index /path/to/repo --clear --semantic
```

Use `--clear` when files have been deleted or renamed, so stale symbols and relationships are removed.

## Incremental indexing (future)

Phase 1 indexes the whole repository. The model is designed to support incremental updates:

- Compare the current commit to the previously indexed commit.
- Re-index only changed, added, renamed, or deleted files.
- Delete stale symbols and relationships for removed files.

This will be implemented in a later phase.
