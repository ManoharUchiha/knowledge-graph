import json
import os
from typing import List, Dict, Any, Optional, Tuple
from repo_intelligence.graph.client import Neo4jClient


def _decode_json_field(record: Dict[str, Any], field: str) -> None:
    if field in record and isinstance(record[field], str):
        try:
            record[field] = json.loads(record[field])
        except json.JSONDecodeError:
            pass


class GraphQueries:
    def __init__(self, client: Neo4jClient):
        self.client = client

    def _run(self, query: str, parameters: Optional[dict] = None) -> List[Dict[str, Any]]:
        results = self.client.execute_query(query, parameters)
        for r in results:
            _decode_json_field(r, "metadata")
            _decode_json_field(r, "evidence")
        return results

    def list_repositories(self) -> List[Dict[str, Any]]:
        query = """
        MATCH (r:Repository)
        RETURN r.name as name, r.root_path as root_path, r.branch as branch,
               r.commit as commit, r.indexed_at as indexed_at
        ORDER BY r.name, r.branch
        """
        return self._run(query)

    def _resolve_repo_from_path(self, file_path: str, repo: Optional[str] = None) -> Tuple[Optional[str], str]:
        """Convert an absolute path to a repo-relative path and return the repo name.

        If `repo` is provided, prefer a repository whose name or root path matches.
        Otherwise return the longest matching root. For relative paths, return
        them unchanged.
        """
        if not file_path.startswith("/"):
            return repo, file_path

        repo_rows = self._run("MATCH (r:Repository) RETURN r.name as repo, r.root_path as root_path")
        repo_rows.sort(key=lambda row: len(row.get("root_path") or ""), reverse=True)

        def repo_matches(row: Dict[str, Any]) -> bool:
            if not repo:
                return True
            name = (row.get("repo") or "").lower()
            root = (row.get("root_path") or "").lower()
            token = repo.lower()
            return token in name or token in root.split("/")

        for row in repo_rows:
            root_path = row.get("root_path") or ""
            if root_path and file_path.startswith(root_path):
                if not repo or repo_matches(row):
                    return row["repo"], os.path.relpath(file_path, root_path)
        return None, file_path

    def _repo_filter(self, repo: Optional[str], branch: Optional[str], commit: Optional[str]) -> str:
        parts = []
        if repo:
            parts.append("s.repo = $repo")
        if branch:
            parts.append("s.branch = $branch")
        if commit:
            parts.append("s.commit = $commit")
        return " AND ".join(parts) if parts else ""

    def find_symbol(
        self,
        name: str,
        repo: Optional[str] = None,
        branch: Optional[str] = None,
        commit: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        where = "s.name = $name"
        repo_where = self._repo_filter(repo, branch, commit)
        if repo_where:
            where += " AND " + repo_where
        if file_path:
            where += " AND s.file_path = $file_path"
        query = f"""
        MATCH (s:Symbol)
        WHERE {where}
        RETURN s.id as id, s.name as name, s.type as type, s.file_path as file_path,
               s.start_line as start_line, s.end_line as end_line
        """
        return self._run(
            query,
            {
                "name": name,
                "repo": repo,
                "branch": branch,
                "commit": commit,
                "file_path": file_path,
            },
        )

    def list_symbols(
        self,
        symbol_type: Optional[str] = None,
        repo: Optional[str] = None,
        branch: Optional[str] = None,
        commit: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        where_parts = ["s.type <> 'file'"]  # optionally exclude raw file nodes
        if symbol_type:
            where_parts.append("s.type = $symbol_type")
        if repo:
            where_parts.append("s.repo = $repo")
        if branch:
            where_parts.append("s.branch = $branch")
        if commit:
            where_parts.append("s.commit = $commit")
        where = " AND ".join(where_parts)
        query = f"""
        MATCH (s:Symbol)
        WHERE {where}
        RETURN s.id as id, s.name as name, s.type as type, s.file_path as file_path,
               s.start_line as start_line, s.end_line as end_line, s.metadata as metadata
        """
        return self._run(
            query,
            {
                "symbol_type": symbol_type,
                "repo": repo,
                "branch": branch,
                "commit": commit,
            },
        )

    def find_file(
        self,
        path: str,
        repo: Optional[str] = None,
        branch: Optional[str] = None,
        commit: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        repo, path = self._resolve_repo_from_path(path, repo)
        where = "f.file_path = $path"
        repo_where = self._repo_filter(repo, branch, commit)
        if repo_where:
            where += " AND " + repo_where.replace("s.", "f.")
        query = f"""
        MATCH (f:File)
        WHERE {where}
        RETURN f.id as id, f.file_path as path
        """
        return self._run(
            query, {"path": path, "repo": repo, "branch": branch, "commit": commit}
        )

    def get_callers(self, symbol_id: str) -> List[Dict[str, Any]]:
        query = """
        MATCH (caller:Symbol)-[r:CALLS]->(s:Symbol {id: $symbol_id})
        RETURN caller.id as id, caller.name as name, caller.type as type,
               caller.file_path as file_path, caller.start_line as line,
               r.confidence as confidence
        """
        return self._run(query, {"symbol_id": symbol_id})

    def get_callees(self, symbol_id: str) -> List[Dict[str, Any]]:
        query = """
        MATCH (s:Symbol {id: $symbol_id})-[r:CALLS]->(callee:Symbol)
        RETURN callee.id as id, callee.name as name, callee.type as type,
               callee.file_path as file_path, callee.start_line as line,
               r.confidence as confidence, r.metadata as metadata
        """
        return self._run(query, {"symbol_id": symbol_id})

    def get_imports(
        self,
        file_id: str,
    ) -> List[Dict[str, Any]]:
        query = """
        MATCH (f:File {id: $file_id})-[:IMPORTS]->(m:Symbol)
        RETURN m.id as id, m.name as name, m.type as type
        """
        return self._run(query, {"file_id": file_id})

    def get_importers(
        self,
        module_id: str,
    ) -> List[Dict[str, Any]]:
        query = """
        MATCH (f:File)-[:IMPORTS]->(m:Symbol {id: $module_id})
        RETURN f.id as id, f.file_path as path
        """
        return self._run(query, {"module_id": module_id})

    def get_dependencies(
        self,
        symbol_id: str,
        depth: int = 5,
    ) -> List[Dict[str, Any]]:
        query = f"""
        MATCH (s:Symbol {{id: $symbol_id}})-[:CALLS|IMPORTS|DEPENDS_ON*1..{depth}]->(dep:Symbol)
        RETURN dep.id as id, dep.name as name, dep.type as type,
               dep.file_path as file_path
        LIMIT 100
        """
        return self._run(query, {"symbol_id": symbol_id})

    def get_dependents(
        self,
        symbol_id: str,
        depth: int = 5,
    ) -> List[Dict[str, Any]]:
        query = f"""
        MATCH (dep:Symbol)-[:CALLS|IMPORTS|DEPENDS_ON*1..{depth}]->(s:Symbol {{id: $symbol_id}})
        RETURN dep.id as id, dep.name as name, dep.type as type,
               dep.file_path as file_path
        LIMIT 100
        """
        return self._run(query, {"symbol_id": symbol_id})

    def trace_execution_flow(
        self,
        start_id: str,
        depth: int = 10,
        max_paths: int = 20,
    ) -> List[Dict[str, Any]]:
        query = f"""
        MATCH p = (start:Symbol {{id: $start_id}})-[:CALLS*1..{depth}]->(end:Symbol)
        RETURN p
        LIMIT $max_paths
        """
        return self._run(
            query, {"start_id": start_id, "max_paths": max_paths}
        )

    def find_xrd_for_kind(
        self,
        kind: str,
        repo: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        where_parts = ["xrd.kind = 'CompositeResourceDefinition'", "t.name = $kind"]
        if repo:
            where_parts.append("xrd.repo = $repo")
        query = f"""
        MATCH (xrd:Symbol)-[:DEFINES]->(t:Symbol {{name: $kind}})
        WHERE {' AND '.join(where_parts)}
        RETURN xrd.id as id, xrd.name as name, xrd.file_path as file_path,
               xrd.repo as repo, xrd.branch as branch
        ORDER BY xrd.repo
        """
        return self._run(query, {"kind": kind, "repo": repo})

    def find_compositions_for_kind(
        self,
        kind: str,
        repo: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        where_parts = ["comp.kind = 'Composition'", "t.name = $kind"]
        if repo:
            where_parts.append("comp.repo = $repo")
        query = f"""
        MATCH (comp:Symbol)-[:COMPOSITES]->(t:Symbol {{name: $kind}})
        WHERE {' AND '.join(where_parts)}
        RETURN comp.id as id, comp.name as name, comp.file_path as file_path,
               comp.repo as repo, comp.branch as branch
        ORDER BY comp.repo
        """
        return self._run(query, {"kind": kind, "repo": repo})

    def get_functions_for_composition(
        self,
        composition_id: str,
    ) -> List[Dict[str, Any]]:
        query = """
        MATCH (comp:Symbol {id: $composition_id})-[:USES]->(fn:Symbol)
        RETURN fn.id as id, fn.name as name, fn.type as type
        """
        return self._run(query, {"composition_id": composition_id})

    def explain_file(
        self,
        file_path: str,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a structured explanation of how a file is implemented.

        For any file: list contained symbols, imports, callers, callees.
        For Crossplane XR files: also trace XRD, Compositions, and Functions.

        `file_path` may be absolute or relative to the repository root.
        """
        # Resolve absolute paths to repository-relative paths.
        original_path = file_path
        repo, file_path = self._resolve_repo_from_path(file_path, repo)
        if file_path.startswith("/"):
            return {
                "error": f"Could not map absolute path to a known repository root: {original_path}",
                "error_code": "REPOSITORY_UNKNOWN",
            }

        repo_where = "f.repo = $repo" if repo else ""
        file_match = "f.file_path = $file_path"
        params = {"file_path": file_path, "repo": repo}

        where = file_match
        if repo_where:
            where += " AND " + repo_where

        # File node and contained symbols
        query = f"""
        MATCH (f:Symbol:File)
        WHERE {where}
        OPTIONAL MATCH (f)-[:CONTAINS]->(s:Symbol)
        RETURN f.id as file_id, f.name as file_name, f.metadata as file_metadata,
               collect(DISTINCT {{
                 id: s.id, name: s.name, type: s.type, kind: s.kind,
                 start_line: s.start_line, end_line: s.end_line
               }}) as symbols
        """
        file_rows = self._run(query, params)
        if not file_rows:
            return {
                "error": f"File not indexed: {file_path}",
                "error_code": "FILE_NOT_INDEXED",
            }
        file_info = file_rows[0]

        symbols = file_info.pop("symbols", [])
        resources = [s for s in symbols if s.get("type") == "resource"]
        classes = [s for s in symbols if s.get("type") == "class"]
        functions = [s for s in symbols if s.get("type") in ("function", "method")]

        # Crossplane trace for each resource in the file
        xrds: List[Dict[str, Any]] = []
        compositions: List[Dict[str, Any]] = []
        functions_used: List[Dict[str, Any]] = []
        for res in resources:
            kind = res.get("kind")
            if kind:
                xrds.extend(self.find_xrd_for_kind(kind, repo=repo))
                compositions.extend(self.find_compositions_for_kind(kind, repo=repo))
        for comp in compositions:
            functions_used.extend(self.get_functions_for_composition(comp["id"]))

        # Python relationships
        callers: List[Dict[str, Any]] = []
        callees: List[Dict[str, Any]] = []
        imports: List[Dict[str, Any]] = []
        inherits: List[Dict[str, Any]] = []
        if classes or functions:
            symbol_ids = [s["id"] for s in symbols if s.get("id")]
            callers = self._run(
                "MATCH (caller:Symbol)-[:CALLS]->(target:Symbol) WHERE target.id IN $ids RETURN caller.name as name, caller.file_path as file_path",
                {"ids": symbol_ids},
            )
            callees = self._run(
                "MATCH (source:Symbol)-[:CALLS]->(callee:Symbol) WHERE source.id IN $ids RETURN callee.name as name, callee.file_path as file_path",
                {"ids": symbol_ids},
            )
            imports = self._run(
                "MATCH (source:Symbol)-[:IMPORTS]->(target:Symbol) WHERE source.id IN $ids RETURN target.name as name, target.file_path as file_path",
                {"ids": symbol_ids},
            )
            inherits = self._run(
                "MATCH (child:Symbol)-[:INHERITS]->(parent:Symbol) WHERE child.id IN $ids RETURN parent.name as name, parent.file_path as file_path",
                {"ids": symbol_ids},
            )

        return {
            "file": file_info,
            "summary": {
                "resources": len(resources),
                "classes": len(classes),
                "functions": len(functions),
            },
            "symbols": symbols,
            "crossplane": {
                "xrds": xrds,
                "compositions": compositions,
                "composition_functions": functions_used,
            },
            "python": {
                "callers": callers,
                "callees": callees,
                "imports": imports,
                "inherits": inherits,
            },
        }
