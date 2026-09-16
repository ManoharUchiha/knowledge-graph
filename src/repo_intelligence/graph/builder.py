import json
from itertools import groupby
from typing import List, Iterable, Any
from repo_intelligence.graph.client import Neo4jClient
from repo_intelligence.models.core import RepositoryModel, Symbol, Relationship, SymbolType


class GraphBuilder:
    def __init__(self, client: Neo4jClient, batch_size: int = 500):
        self.client = client
        self.batch_size = batch_size

    def build(self, model: RepositoryModel):
        # 1. Ensure indexes exist for fast MERGE operations.
        self._setup_indexes()

        # 2. Repository node
        self._upsert_repository(model)

        # 3. Separate file symbols from other symbols.
        file_symbols = [s for s in model.symbols if s.symbol_type == SymbolType.FILE]
        other_symbols = [s for s in model.symbols if s.symbol_type != SymbolType.FILE]

        # 4. Batch create file nodes.
        self._batch_create_symbols(file_symbols, with_file_label=True)

        # 5. Batch create other symbols and link them to their files.
        self._batch_create_symbols(other_symbols, with_file_label=False)

        # 6. Link repository to each file in batches.
        self._batch_link_repository_to_files(model)

        # 7. Batch create relationships, grouped by type.
        self._batch_create_relationships(model.relationships)

    def _setup_indexes(self):
        # Indexes on the unique id fields dramatically speed up MERGE.
        index_queries = [
            "CREATE CONSTRAINT symbol_id_unique IF NOT EXISTS FOR (s:Symbol) REQUIRE s.id IS UNIQUE",
            "CREATE INDEX symbol_repo_idx IF NOT EXISTS FOR (s:Symbol) ON (s.repo, s.branch, s.commit)",
            "CREATE INDEX symbol_kind_idx IF NOT EXISTS FOR (s:Symbol) ON (s.kind)",
            "CREATE INDEX symbol_type_name_idx IF NOT EXISTS FOR (s:Symbol) ON (s.type, s.name)",
            "CREATE INDEX repository_snapshot_idx IF NOT EXISTS FOR (r:Repository) ON (r.name, r.branch, r.commit)",
        ]
        for query in index_queries:
            try:
                self.client.execute_query(query)
            except Exception as e:  # pylint: disable=broad-except
                # Log but do not fail indexing if indexes cannot be created.
                print(f"[graph] index setup warning: {e}")

    def _upsert_repository(self, model: RepositoryModel):
        query = """
        MERGE (r:Repository {name: $repo_name, branch: $branch})
        SET r.commit = $commit, r.root_path = $root_path, r.indexed_at = datetime()
        """
        params = {
            "repo_name": model.repo_name,
            "branch": model.branch,
            "commit": model.commit,
            "root_path": model.root_path,
        }
        self.client.execute_query(query, params)

    def _batch_create_symbols(self, symbols: List[Symbol], with_file_label: bool):
        if not symbols:
            return

        if with_file_label:
            # File nodes carry the :Symbol:File label combination.
            query = """
            UNWIND $symbols AS sym
            MERGE (n:Symbol:File {id: sym.id})
            SET n = sym
            """
        else:
            # For other symbols, also MERGE their containing file and link it.
            query = """
            UNWIND $symbols AS sym
            MERGE (f:Symbol:File {id: sym.file_id})
            MERGE (n:Symbol {id: sym.id})
            SET n = sym
            MERGE (f)-[:CONTAINS]->(n)
            """

        for batch in self._chunks(symbols, self.batch_size):
            params = {"symbols": [self._symbol_to_dict(s, include_file_id=not with_file_label) for s in batch]}
            self.client.execute_query(query, params)

    def _batch_link_repository_to_files(self, model: RepositoryModel):
        if not model.files:
            return

        query = """
        MATCH (r:Repository {name: $repo_name, branch: $branch})
        WITH r
        UNWIND $file_ids AS file_id
        MATCH (f:Symbol:File {id: file_id})
        MERGE (r)-[:CONTAINS]->(f)
        """
        file_ids = [
            self._make_file_id(model.repo_name, model.branch, f.path)
            for f in model.files
        ]
        for batch in self._chunks(file_ids, self.batch_size):
            self.client.execute_query(
                query,
                {
                    "repo_name": model.repo_name,
                    "branch": model.branch,
                    "file_ids": batch,
                },
            )

    def _batch_create_relationships(self, relationships: List[Relationship]):
        if not relationships:
            return

        # Group by relationship type so we can interpolate the type safely.
        relationships.sort(key=lambda r: r.rel_type.value)
        for rel_type, group_iter in groupby(relationships, key=lambda r: r.rel_type.value):
            group = list(group_iter)
            query = f"""
            UNWIND $rels AS row
            MERGE (source:Symbol {{id: row.source_id}})
            ON CREATE SET source += row.source_stub
            MERGE (target:Symbol {{id: row.target_id}})
            ON CREATE SET target += row.target_stub
            MERGE (source)-[r:{rel_type}]->(target)
            SET r.confidence = row.confidence,
                r.evidence = row.evidence,
                r.metadata = row.metadata,
                r.resolution_status = row.resolution_status,
                r.resolver = row.resolver,
                r.repo = row.repo,
                r.branch = row.branch,
                r.commit = row.commit
            """
            for batch in self._chunks(group, self.batch_size):
                params = {"rels": [self._relationship_to_dict(r) for r in batch]}
                self.client.execute_query(query, params)

    @staticmethod
    def _symbol_to_dict(symbol: Symbol, include_file_id: bool = False) -> dict:
        data = {
            "id": symbol.id,
            "repo": symbol.repo,
            "branch": symbol.branch,
            "commit": symbol.commit,
            "name": symbol.name,
            "type": symbol.symbol_type.value,
            "kind": symbol.metadata.get("kind"),
            "group": symbol.metadata.get("group"),
            "file_path": symbol.location.file_path,
            "start_line": symbol.location.start_line,
            "start_col": symbol.location.start_col,
            "end_line": symbol.location.end_line,
            "end_col": symbol.location.end_col,
            "parent_id": symbol.parent_id,
            "metadata": json.dumps(symbol.metadata),
        }
        if include_file_id:
            data["file_id"] = GraphBuilder._make_file_id(
                symbol.repo, symbol.branch, symbol.location.file_path
            )
        return data

    @staticmethod
    def _relationship_to_dict(rel: Relationship) -> dict:
        return {
            "source_id": rel.source_id,
            "target_id": rel.target_id,
            "source_stub": GraphBuilder._endpoint_stub(rel.source_id),
            "target_stub": GraphBuilder._endpoint_stub(rel.target_id),
            "confidence": rel.confidence,
            "evidence": json.dumps([e.model_dump() for e in rel.evidence]),
            "metadata": json.dumps(rel.metadata),
            "resolution_status": rel.metadata.get("resolution_status"),
            "resolver": rel.metadata.get("resolver"),
            "repo": rel.repo,
            "branch": rel.branch,
            "commit": rel.commit,
        }

    @staticmethod
    def _endpoint_stub(node_id: str) -> dict:
        """Minimal properties applied (ON CREATE only) to a relationship endpoint.

        Prevents bare, unlabelled phantom nodes: endpoints that are not defined
        elsewhere still carry a ``category``/``type``/``name`` so the graph stays
        queryable and unresolved edges are easy to filter out. Real symbol nodes
        are created earlier in ``build`` and are never overwritten (ON CREATE).
        """
        prefixes = {
            "module:": ("external", "module"),
            "unresolved:": ("unresolved", "unknown"),
            "fn:": ("external", "function_ref"),
            "xrdtype:": ("placeholder", "resource_type"),
        }
        for prefix, (category, node_type) in prefixes.items():
            if node_id.startswith(prefix):
                remainder = node_id[len(prefix):]
                name = remainder.split(":")[-1] if node_type == "resource_type" else remainder
                return {"category": category, "type": node_type, "name": name}
        # A concrete symbol id referenced before/without its own definition.
        return {"category": "symbol_ref"}

    @staticmethod
    def _chunks(items: Iterable[Any], size: int):
        chunk = []
        for item in items:
            chunk.append(item)
            if len(chunk) == size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk

    @staticmethod
    def _make_file_id(repo: str, branch: str, file_path: str) -> str:
        return f"{repo}:{branch}:{file_path}"
