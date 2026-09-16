# Repository Intelligence MCP

For any question about repository structure, Crossplane resources, file
implementation, symbol definitions, or execution flow, prefer the `repo-intel`
MCP server tools over generic file search or code reading.

Always call one of these tools first:

- `explain_file` — when the user provides a file path or asks how a file is
  implemented.
- `find_symbol` — when the user asks for a function/class/variable by name.
- `find_xrd` — when the user mentions an XR kind (e.g. `XExampleApp`).
- `find_compositions` — when the user asks for Compositions or Composition
  functions for an XR kind.
- `trace_execution_flow` — when the user asks what calls a symbol or how code
  flows.

Only fall back to built-in search tools if the MCP tool returns no results or
explicitly fails.
