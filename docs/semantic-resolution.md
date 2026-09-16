# Phase 2 — Semantic Code Intelligence

Phase 2 enriches the syntactic graph from Phase 1 with semantic relationships.

## Goals

- Resolve call targets across files when possible.
- Extract inheritance and type-reference relationships.
- Provide a pluggable backend architecture for SCIP, LSP, and Joern.

## Architecture

```
RepositoryModel (from Tree-sitter parsers)
  ↓
Static resolver (module-level import resolution)
  ↓
SemanticResolver backend (Jedi / SCIP / LSP / Joern)
  ↓
GraphBuilder
```

The `SemanticResolver` abstraction lives in `src/repo_intelligence/semantic/`.

## Backends

| Backend | Status | Purpose |
|---------|--------|---------|
| `jedi` | Implemented | Python static analysis for cross-file calls, inheritance, and type references. |
| `scip` | Stub | Future ingestion of SCIP indexes. |
| `lsp` | Stub | Future integration with a language server. |
| `joern` | Stub | Future integration for C/C++/Java/JVM code. |

## Usage

Enable semantic resolution during indexing:

```bash
repo-intel index /path/to/repo --semantic
repo-intel index /path/to/repo --semantic --semantic-backend jedi
```

## What Jedi resolves

- `INHERITS` relationships: `class Child(Base)` → resolved to the `Base` class symbol.
- `CALLS` relationships: bare function/method calls and attribute calls resolved to their definitions when Jedi can determine them.

Each resolved relationship receives:

- `confidence = 0.95`
- `metadata.resolution_status = "jedi-resolved"`
- an additional `Evidence` entry of type `"jedi"`

## Design notes

- Semantic resolution is opt-in because it requires extra CPU and may fail for dynamic or heavily meta-programmed code.
- Unresolved targets remain in the graph as `unresolved:<name>` with lower confidence.
- The backend interface is intentionally small so SCIP/LSP/Joern implementations can be swapped in later.
