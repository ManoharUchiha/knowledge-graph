# MCP (`repo-intel`) vs. Devin built-in tools

This project exposes repository intelligence through an MCP server (`repo-intel`) backed by a persistent Neo4j graph. Devin can also use its own built-in file search and code reading tools. This table helps decide when to use which.

## Quick comparison

| Aspect | `repo-intel` MCP server | Devin built-in tools |
|--------|-------------------------|----------------------|
| **Knowledge source** | Pre-indexed Neo4j graph with parsed symbols and relationships | Live filesystem + model’s training data |
| **Setup required** | Index the repo once (`repo-intel index /path/to/repo`), Neo4j running | None — works out of the box |
| **Scope** | Any repo that has been indexed; supports multiple repos in one graph | Only the files Devin reads during the session |
| **Crossplane awareness** | Understands XRD → XR kind → Composition → Function pipelines | Generic YAML/text understanding only |
| **Speed** | Fast graph queries, even across large codebases | Can be slow for deep questions over many files |
| **Determinism** | Returns structured, evidence-backed facts (file paths, line ranges, IDs) | Answers depend on what the model read and inferred |
| **Freshness** | Reflects the last indexed snapshot; must re-index after big changes | Always sees the current filesystem state |
| **Tool surface** | Limited to implemented tools (`explain_file`, `find_symbol`, `trace_execution_flow`, etc.) | Broad and flexible — can read any file, run shell commands, search web |
| **Unindexed files** | Cannot answer unless re-indexed | Can read and reason about any file |
| **Reasoning** | Best for “what is wired to what” and “where is this defined” | Best for open-ended interpretation, refactoring, and synthesis |

## When to prefer `repo-intel`

- You want exact facts: *Which XRD defines `XExampleApp`? Which Composition implements it? Which functions run in its pipeline?*
- You are exploring a large repo and want fast, multi-hop relationships without re-reading files.
- You need consistent, repeatable answers backed by source locations.
- You are comparing or tracing relationships across multiple indexed repositories.

## When to prefer Devin built-in tools

- You have not indexed the repo yet. (Note: a single new or changed file is now
  indexed automatically by `explain_file`; a full initial index is still manual.)
- The question is open-ended: *“Refactor this function”* or *“Explain the design of this module”*.
- You need to read arbitrary files (logs, docs, generated artifacts) that are not in the graph.
- You want shell commands, tests, or web searches as part of the answer.

## Recommended hybrid workflow

1. **Index once** for any repo you work with regularly.
2. **Start with MCP** for structural/relationship questions:
   - *“How is this file implemented?”*
   - *“What calls this function?”*
   - *“Which Composition handles this XR kind?”*
3. **Fall back to Devin tools** when:
   - The MCP tool returns no results (unindexed file or unsupported language).
   - The question requires interpretation, editing, or live filesystem state.

## Example

| Question | Best tool |
|----------|-----------|
| *How is `example-resource.yaml` implemented?* | `repo-intel` `explain_file` |
| *What calls `create_order` in `main.py`?* | `repo-intel` `find_symbol` + `trace_execution_flow` |
| *Refactor `create_order` to accept a config object.* | Devin built-in editing tools |
| *Why is this test failing today?* | Devin built-in (read logs, run tests) |
| *Which repo defines the `XExampleApp` kind?* | `repo-intel` `find_xrd` across indexed repos |
