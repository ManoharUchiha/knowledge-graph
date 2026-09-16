from repo_intelligence.graph.builder import GraphBuilder


def test_endpoint_stub_annotates_external_and_unresolved_targets():
    assert GraphBuilder._endpoint_stub("module:requests") == {
        "category": "external",
        "type": "module",
        "name": "requests",
    }
    assert GraphBuilder._endpoint_stub("unresolved:self.foo") == {
        "category": "unresolved",
        "type": "unknown",
        "name": "self.foo",
    }
    assert GraphBuilder._endpoint_stub("fn:function-x") == {
        "category": "external",
        "type": "function_ref",
        "name": "function-x",
    }
    assert GraphBuilder._endpoint_stub("xrdtype:example.org:XWidget") == {
        "category": "placeholder",
        "type": "resource_type",
        "name": "XWidget",
    }


def test_endpoint_stub_for_concrete_symbol_is_symbol_ref():
    assert GraphBuilder._endpoint_stub("repo:main:m.py:C.method") == {"category": "symbol_ref"}


def test_relationship_dict_includes_endpoint_stubs():
    from repo_intelligence.models.core import Relationship, RelationType

    rel = Relationship(
        source_id="repo:main:m.py:f",
        target_id="unresolved:mystery",
        rel_type=RelationType.CALLS,
        repo="repo",
        branch="main",
        commit="c",
    )
    data = GraphBuilder._relationship_to_dict(rel)
    assert data["source_stub"] == {"category": "symbol_ref"}
    assert data["target_stub"]["category"] == "unresolved"


def test_file_id_has_no_commit():
    assert GraphBuilder._make_file_id("repo", "main", "src/app.py") == "repo:main:src/app.py"
