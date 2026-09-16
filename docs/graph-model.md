# Graph Model

## Node labels

All nodes carry the `Symbol` label. Some nodes carry an additional label derived from their type:

| Label | Meaning |
|-------|---------|
| `Symbol:Repository` | Indexed repository snapshot |
| `Symbol:File` | A scanned file |
| `Symbol` (with `type` property) | A function, class, method, module, or resource |

## Node properties

| Property | Description |
|----------|-------------|
| `id` | Unique identifier scoped to repo/branch/commit |
| `repo` | Repository name |
| `branch` | Git branch |
| `commit` | Git commit hash |
| `name` | Human-readable symbol name |
| `type` | Symbol type (`function`, `class`, `method`, `module`, `resource`, `file`, ...) |
| `file_path` | Relative path within the repository |
| `start_line` / `start_col` | Start position in source |
| `end_line` / `end_col` | End position in source |
| `parent_id` | For methods: the containing class symbol id |
| `metadata` | JSON-encoded extra attributes (kind, resource_type, size, language) |

## Relationship types

| Type | Meaning |
|------|---------|
| `CONTAINS` | File → symbol, Repository → file |
| `DEFINES` | File → class/function, Class → method |
| `IMPORTS` | File → imported module |
| `CALLS` | Function/method/file → callee |
| `KUBERNETES_OBJECT` | File → Kubernetes object |
| `CREATES` | Terraform file → resource/module |

## Relationship properties

| Property | Description |
|----------|-------------|
| `confidence` | 0.0–1.0; higher for resolved local calls |
| `evidence` | JSON-encoded list of evidence objects (type, file, lines) |
| `metadata` | JSON-encoded extra attributes (callee name, resolution status) |

## Example subgraph

```text
(:Repository {name: "myproject"})-[:CONTAINS]->(:File {path: "main.py"})
(:File {path: "main.py"})-[:DEFINES]->(:Symbol {name: "main", type: "function"})
(:Symbol {name: "main"})-[:CALLS {confidence: 0.95}]->(:Symbol {name: "create_order"})
```
