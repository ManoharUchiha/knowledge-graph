import hashlib
from unittest.mock import patch

from repo_intelligence.indexer import FileIndexer
from repo_intelligence.models.core import make_file_id


XRD = """apiVersion: apiextensions.crossplane.io/v1
kind: CompositeResourceDefinition
metadata:
  name: xdatabases.example.org
spec:
  group: example.org
  names:
    kind: XDatabase
    plural: xdatabases
"""


def repository_row(root_path):
    return {
        "name": "test-repo",
        "root_path": str(root_path),
        "branch": "main",
        "commit": "abc123",
        "indexed_at": "now",
    }


class FakeClient:
    """Minimal Neo4j stand-in that answers the indexer's read queries."""

    def __init__(self, repo_row, file_nodes=None):
        self.repo_row = repo_row
        self.file_nodes = file_nodes or {}
        self.queries = []

    def execute_query(self, query, parameters=None):
        params = parameters or {}
        self.queries.append((" ".join(query.split()), params))
        normalized = " ".join(query.split())
        if "MATCH (r:Repository)" in normalized:
            return [self.repo_row]
        if "Symbol:File {id: $file_id}" in normalized:
            metadata = self.file_nodes.get(params.get("file_id"))
            return [{"metadata": metadata}] if metadata is not None else []
        return []

    def delete_queries(self):
        return [(q, p) for q, p in self.queries if "DETACH DELETE" in q]


def write_xrd(tmp_path):
    xrd = tmp_path / "apis" / "database.yaml"
    xrd.parent.mkdir()
    xrd.write_text(XRD)
    return xrd


def file_id_for(relative_path="apis/database.yaml"):
    return make_file_id("test-repo", "main", relative_path)


def hash_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_indexes_a_new_xrd_file(tmp_path):
    xrd = write_xrd(tmp_path)
    client = FakeClient(repository_row(tmp_path))

    with patch("repo_intelligence.indexer.GraphBuilder.build") as build:
        result = FileIndexer(client).index_file(str(xrd))

    assert result["indexed"] is True
    assert result["action"] == "created"
    assert result["file_path"] == "apis/database.yaml"
    assert result["content_hash"] == hash_of(xrd)
    assert client.delete_queries() == []
    model = build.call_args.args[0]
    assert any(symbol.metadata.get("kind") == "XDatabase" for symbol in model.symbols)
    assert any(relationship.rel_type.value == "DEFINES" for relationship in model.relationships)
    file_symbol = next(s for s in model.symbols if s.symbol_type.value == "file")
    assert file_symbol.metadata["content_hash"] == hash_of(xrd)


def test_up_to_date_file_is_not_reindexed(tmp_path):
    xrd = write_xrd(tmp_path)
    client = FakeClient(
        repository_row(tmp_path),
        file_nodes={file_id_for(): {"content_hash": hash_of(xrd)}},
    )

    with patch("repo_intelligence.indexer.GraphBuilder.build") as build:
        result = FileIndexer(client).index_file(str(xrd))

    assert result["indexed"] is False
    assert result["up_to_date"] is True
    build.assert_not_called()
    assert client.delete_queries() == []


def test_changed_file_is_refreshed_and_stale_symbols_removed(tmp_path):
    xrd = write_xrd(tmp_path)
    client = FakeClient(
        repository_row(tmp_path),
        file_nodes={file_id_for(): {"content_hash": "stale-hash"}},
    )

    with patch("repo_intelligence.indexer.GraphBuilder.build") as build:
        result = FileIndexer(client).index_file(str(xrd))

    assert result["indexed"] is True
    assert result["action"] == "refreshed"
    build.assert_called_once()
    deletes = client.delete_queries()
    assert len(deletes) == 1
    assert deletes[0][1]["prefix"] == f"{file_id_for()}:"


def test_force_reindexes_even_when_unchanged(tmp_path):
    xrd = write_xrd(tmp_path)
    client = FakeClient(
        repository_row(tmp_path),
        file_nodes={file_id_for(): {"content_hash": hash_of(xrd)}},
    )

    with patch("repo_intelligence.indexer.GraphBuilder.build") as build:
        result = FileIndexer(client).index_file(str(xrd), force=True)

    assert result["indexed"] is True
    assert result["action"] == "refreshed"
    build.assert_called_once()
    assert len(client.delete_queries()) == 1


def test_legacy_indexed_file_without_hash_is_refreshed(tmp_path):
    xrd = write_xrd(tmp_path)
    client = FakeClient(
        repository_row(tmp_path),
        file_nodes={file_id_for(): {"language": "yaml"}},
    )

    with patch("repo_intelligence.indexer.GraphBuilder.build") as build:
        result = FileIndexer(client).index_file(str(xrd))

    assert result["indexed"] is True
    assert result["action"] == "refreshed"
    build.assert_called_once()


def test_rejects_path_outside_indexed_repository(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.write_text(XRD)
    client = FakeClient(repository_row(repository))

    result = FileIndexer(client).index_file(str(outside))

    assert result["error_code"] == "FILE_OUTSIDE_REPOSITORY"


def test_relative_path_requires_repository():
    client = FakeClient(repository_row("/tmp/repo"))

    result = FileIndexer(client).index_file("apis/database.yaml")

    assert result["error_code"] == "REPOSITORY_REQUIRED"
    assert client.queries == []


def test_recognized_but_unparsed_file_is_indexed_as_file_node(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# Docs\n")
    client = FakeClient(repository_row(tmp_path))

    with patch("repo_intelligence.indexer.GraphBuilder.build") as build:
        result = FileIndexer(client).index_file(str(readme))

    assert result["indexed"] is True
    model = build.call_args.args[0]
    # Only the file node itself, no parsed symbols.
    assert len(model.symbols) == 1
    assert model.symbols[0].symbol_type.value == "file"


def test_truly_unknown_extension_is_rejected(tmp_path):
    binary = tmp_path / "thing.xyz"
    binary.write_text("data")
    client = FakeClient(repository_row(tmp_path))

    result = FileIndexer(client).index_file(str(binary))

    assert result["error_code"] == "UNSUPPORTED_FILE_TYPE"
