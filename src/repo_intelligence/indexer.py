from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Optional, Tuple

from repo_intelligence.config import DEFAULT_IGNORE_DIRS, EXTENSION_TO_LANGUAGE
from repo_intelligence.graph.builder import GraphBuilder
from repo_intelligence.graph.client import Neo4jClient
from repo_intelligence.models.core import FileInfo, RepositoryModel, SourceLocation, Symbol, SymbolType, make_file_id
from repo_intelligence.parsers.base import ParserContext
from repo_intelligence.parsers.factory import ParserFactory
from repo_intelligence.resolver import resolve_relationships


class FileIndexer:
    def __init__(self, client: Neo4jClient, max_file_size: int = 5 * 1024 * 1024):
        self.client = client
        self.max_file_size = max_file_size

    def index_file(self, file_path: str, repo: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        """Index (or refresh) a single file in the graph.

        When the file is already indexed and its content is unchanged the graph
        is left untouched and ``up_to_date`` is reported. When the content has
        changed (or ``force`` is set) the file's previously indexed symbols are
        removed and the file is re-parsed so the graph stays current.
        """
        resolved = self._resolve_file(file_path, repo)
        if "error" in resolved:
            return resolved

        repository, absolute_path, relative_path = resolved["repository"], resolved["absolute_path"], resolved["relative_path"]
        try:
            with open(absolute_path, "rb") as source_file:
                source_bytes = source_file.read()
        except OSError as exc:
            return self._error("FILE_UNREADABLE", f"Could not read file: {exc}")
        if len(source_bytes) > self.max_file_size:
            return self._error("FILE_TOO_LARGE", f"File exceeds the {self.max_file_size}-byte indexing limit")

        extension = os.path.splitext(relative_path)[1].lower()
        language = EXTENSION_TO_LANGUAGE.get(extension)
        if not language:
            return self._error("UNSUPPORTED_FILE_TYPE", f"Unrecognized file type: {extension or relative_path}")
        # A recognized language without a parser (e.g. markdown/json) is still
        # indexed as a file node, matching a full repository index.
        has_parser = ParserFactory.supports(language)

        context = ParserContext(
            repo_name=repository["name"],
            root_path=repository["root_path"],
            branch=repository["branch"],
            commit=repository["commit"],
        )
        file_id = make_file_id(context.repo_name, context.branch, relative_path)
        content_hash = hashlib.sha256(source_bytes).hexdigest()

        existing_hash = self._existing_file_hash(file_id)
        already_indexed = existing_hash is not None
        if already_indexed and existing_hash == content_hash and not force:
            return {
                "indexed": False,
                "up_to_date": True,
                "repo": context.repo_name,
                "file_path": relative_path,
                "content_hash": content_hash,
            }

        file_info = FileInfo(path=relative_path, language=language, size=len(source_bytes))
        file_symbol = Symbol(
            id=file_id,
            repo=context.repo_name,
            branch=context.branch,
            commit=context.commit,
            name=relative_path,
            symbol_type=SymbolType.FILE,
            location=SourceLocation(
                file_path=relative_path,
                start_line=1,
                start_col=0,
                end_line=1,
                end_col=0,
            ),
            metadata={"language": language, "size": len(source_bytes), "content_hash": content_hash},
        )

        try:
            if has_parser:
                symbols, relationships = ParserFactory.get_parser(language, context).parse(relative_path, source_bytes)
            else:
                symbols, relationships = [], []
            model = resolve_relationships(
                RepositoryModel(
                    repo_name=context.repo_name,
                    root_path=context.root_path,
                    branch=context.branch,
                    commit=context.commit,
                    files=[file_info],
                    symbols=[file_symbol, *symbols],
                    relationships=relationships,
                )
            )
            if already_indexed:
                self._remove_file_symbols(file_id)
            GraphBuilder(self.client).build(model)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return self._error("INDEXING_FAILED", f"Failed to index {relative_path}: {exc}")

        return {
            "indexed": True,
            "action": "refreshed" if already_indexed else "created",
            "repo": context.repo_name,
            "file_path": relative_path,
            "content_hash": content_hash,
            "symbols": len(model.symbols),
            "relationships": len(model.relationships),
        }

    def _existing_file_hash(self, file_id: str) -> Optional[str]:
        """Return the stored content hash for an indexed file, or None if absent.

        An indexed file that predates content-hash tracking returns an empty
        string so it is always treated as stale and refreshed on next access.
        """
        rows = self.client.execute_query(
            "MATCH (f:Symbol:File {id: $file_id}) RETURN f.metadata as metadata",
            {"file_id": file_id},
        )
        if not rows:
            return None
        metadata = rows[0].get("metadata")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        if not isinstance(metadata, dict):
            return ""
        return metadata.get("content_hash") or ""

    def _remove_file_symbols(self, file_id: str) -> None:
        """Delete symbols owned by a file before re-indexing it.

        Only nodes whose id is prefixed with the file id are removed, so shared
        placeholder nodes (e.g. ``xrdtype:...`` or ``fn:...`` referenced by other
        files) and the file node itself are preserved.
        """
        self.client.execute_query(
            "MATCH (n:Symbol) WHERE n.id STARTS WITH $prefix DETACH DELETE n",
            {"prefix": f"{file_id}:"},
        )

    def _resolve_file(self, file_path: str, repo: Optional[str]) -> Dict[str, Any]:
        if not os.path.isabs(file_path) and not repo:
            return self._error("REPOSITORY_REQUIRED", "repo is required when indexing a relative file path")
        repositories = self.client.execute_query(
            """
            MATCH (r:Repository)
            RETURN r.name as name, r.root_path as root_path, r.branch as branch,
                   r.commit as commit, r.indexed_at as indexed_at
            ORDER BY r.indexed_at DESC
            """
        )
        candidates = [row for row in repositories if self._repo_matches(row, repo)]
        if not candidates:
            return self._error("REPOSITORY_UNKNOWN", f"No indexed repository matches {repo or file_path}")

        match = self._match_path(file_path, candidates)
        if not match:
            return self._error("FILE_OUTSIDE_REPOSITORY", "File is not inside a matching indexed repository")
        repository, absolute_path, relative_path = match
        if not os.path.isfile(absolute_path):
            return self._error("FILE_DOES_NOT_EXIST", f"File does not exist: {absolute_path}")
        if any(part in DEFAULT_IGNORE_DIRS for part in relative_path.split(os.sep)):
            return self._error("FILE_IGNORED", f"File is inside an ignored directory: {relative_path}")
        return {
            "repository": repository,
            "absolute_path": absolute_path,
            "relative_path": relative_path,
        }

    @staticmethod
    def _repo_matches(repository: Dict[str, Any], repo: Optional[str]) -> bool:
        if not repo:
            return True
        token = repo.lower()
        name = (repository.get("name") or "").lower()
        root = (repository.get("root_path") or "").lower()
        return token == name or token == os.path.basename(root)

    @staticmethod
    def _match_path(file_path: str, repositories: list[Dict[str, Any]]) -> Optional[Tuple[Dict[str, Any], str, str]]:
        absolute_input = os.path.isabs(file_path)
        input_path = os.path.realpath(file_path) if absolute_input else file_path
        for repository in repositories:
            root_path = os.path.realpath(repository.get("root_path") or "")
            if not root_path:
                continue
            absolute_path = input_path if absolute_input else os.path.realpath(os.path.join(root_path, file_path))
            try:
                if os.path.commonpath((root_path, absolute_path)) != root_path:
                    continue
            except ValueError:
                continue
            return repository, absolute_path, os.path.relpath(absolute_path, root_path)
        return None

    @staticmethod
    def _error(code: str, message: str) -> Dict[str, Any]:
        return {"error": message, "error_code": code}
