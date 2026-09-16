# Architecture

## Goal

The Repository Intelligence Platform pre-computes a structured, persistent model of a codebase so LLM coding agents can query relationships instead of repeatedly scanning source files.

## Phase 1 design

```
Repository
  ↓
Scanner  →  discovers files, filters noise, detects language
  ↓
Parser registry  →  Python, YAML, HCL/Terraform Tree-sitter parsers
  ↓
Intermediate model  →  Pydantic symbols & relationships
  ↓
Resolver  →  maps imported module names to local file symbols
  ↓
Neo4j GraphBuilder  →  persistent property graph
  ↓
GraphQueries / CLI  →  callers, callees, imports, execution flow
```

## Key principles

1. **Graph is the source of truth for relationships.** Relationships such as `CALLS`, `IMPORTS`, `DEFINES`, `CREATES`, and `KUBERNETES_OBJECT` are extracted by static analysis, not inferred by embeddings.
2. **Source code remains the source of truth.** Graph nodes store file path, line numbers, commit, and branch so the exact source region can be retrieved on demand.
3. **Evidence-backed relationships.** Every relationship carries confidence and source evidence.
4. **No semantic over-claiming.** Call resolution is syntactic/module-level in Phase 1. Unresolved targets are stored as `unresolved:<name>` with low confidence.
5. **Git-aware indexing.** Each indexing run records `repo`, `branch`, and `commit` on every symbol and relationship.

## Future extension points

- `SCIP` / `LSP` / `Joern` can be added as additional evidence sources to improve cross-file call resolution.
- `Qdrant` can index semantic units (functions, classes, docs) for hybrid retrieval.
- `PostgreSQL` can store investigations, decisions, and incidents (memory layer).
- `OpenTelemetry` can add runtime evidence as a separate relationship source.
