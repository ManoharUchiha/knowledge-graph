# Parsers

All parsers implement `BaseParser` and receive a `ParserContext` containing repository metadata (`repo_name`, `root_path`, `branch`, `commit`). They return `(List[Symbol], List[Relationship])`.

## Supported languages

| Language | Extension | Parser module | Tree-sitter grammar |
|----------|-----------|---------------|---------------------|
| Python | `.py` | `parsers/python.py` | `tree-sitter-python` |
| YAML | `.yaml`, `.yml` | `parsers/yaml.py` | `tree-sitter-yaml` |
| HCL / Terraform | `.tf`, `.tfvars`, `.hcl` | `parsers/terraform.py` | `tree-sitter-hcl` |

## Python parser

Extracts:

- Classes (`SymbolType.CLASS`)
- Functions and methods (`SymbolType.FUNCTION`, `SymbolType.METHOD`)
- Imports (`IMPORTS` relationship)
- Call expressions (`CALLS` relationship)

Call resolution is syntactic/module-level. Bare calls to names imported from another module are resolved to `module:<module>.<name>`; the resolver then maps these to local file symbols when possible. Calls through local instances (e.g., `service.create_order()`) remain unresolved.

## YAML parser

Parses YAML documents (including multi-document files). If a document contains `apiVersion` and `kind`, it is emitted as a `RESOURCE` symbol and linked to its file via `KUBERNETES_OBJECT`.

### Crossplane-specific extraction

For Crossplane resources, the parser also extracts:

| Source | Relationship | Target |
|--------|--------------|--------|
| `CompositeResourceDefinition` | `DEFINES` | composite XR kind (`RESOURCE_TYPE`) |
| `Composition` | `COMPOSITES` | referenced composite kind (`RESOURCE_TYPE`) |
| `Composition` | `USES` | pipeline `Function` references |

## Terraform/HCL parser

Parses top-level blocks. Currently extracts:

- `resource` blocks → `RESOURCE` symbol
- `module` blocks → `MODULE` symbol

A `CREATES` relationship is created from the file to the resource/module.

## Adding a new parser

1. Create a new module in `src/repo_intelligence/parsers/`.
2. Subclass `BaseParser` and implement `parse`.
3. Register the parser in `parsers/factory.py`.
