import pytest
from repo_intelligence.parsers.base import ParserContext
from repo_intelligence.parsers.python import PythonParser
from repo_intelligence.parsers.yaml import YamlParser
from repo_intelligence.parsers.terraform import TerraformParser
from repo_intelligence.parsers.go import GoParser
from repo_intelligence.models.core import SymbolType, RelationType


@pytest.fixture
def ctx():
    return ParserContext(
        repo_name="test-repo",
        root_path="/tmp/test-repo",
        branch="main",
        commit="abc1234",
    )


def test_python_parser_extracts_function_and_class(ctx):
    parser = PythonParser(ctx)
    code = b"def hello(): pass\nclass MyClass:\n    def method(self): pass"
    symbols, relationships = parser.parse("test.py", code)

    by_type = {s.symbol_type: s for s in symbols}
    assert SymbolType.FUNCTION in by_type
    assert SymbolType.CLASS in by_type
    assert SymbolType.METHOD in by_type
    assert by_type[SymbolType.FUNCTION].name == "hello"
    assert by_type[SymbolType.METHOD].parent_id == by_type[SymbolType.CLASS].id


def test_python_parser_imports(ctx):
    parser = PythonParser(ctx)
    code = b"import requests\nfrom services.order import create_order"
    symbols, relationships = parser.parse("main.py", code)

    imports = [r for r in relationships if r.rel_type == RelationType.IMPORTS]
    assert len(imports) == 2
    module_names = {r.target_id for r in imports}
    assert "module:requests" in module_names
    assert "module:services.order" in module_names


def test_python_parser_call_resolution(ctx):
    parser = PythonParser(ctx)
    code = b"from services.order import create_order\n\ndef main():\n    create_order()"
    symbols, relationships = parser.parse("main.py", code)

    calls = [r for r in relationships if r.rel_type == RelationType.CALLS]
    assert len(calls) == 1
    assert "module:services.order.create_order" in calls[0].target_id


def _call_targets(parser, path, code):
    _, rels = parser.parse(path, code)
    return [r.target_id for r in rels if r.rel_type == RelationType.CALLS]


def test_python_dotted_import_call_does_not_duplicate_path(ctx):
    parser = PythonParser(ctx)
    targets = _call_targets(parser, "m.py", b"import a.b.c\n\ndef f():\n    a.b.c.func()")
    assert targets == ["module:a.b.c.func"]


def test_python_aliased_import_call(ctx):
    parser = PythonParser(ctx)
    targets = _call_targets(parser, "m.py", b"import a.b.c as x\n\ndef f():\n    x.func()")
    assert targets == ["module:a.b.c.func"]


def test_python_self_method_call_resolves_to_class_method(ctx):
    parser = PythonParser(ctx)
    code = b"class C:\n    def a(self):\n        self.b()\n    def b(self):\n        pass"
    targets = _call_targets(parser, "m.py", code)
    assert any(t.endswith("m.py:C.b") and not t.startswith("unresolved:") for t in targets)


def test_python_local_inheritance_resolves(ctx):
    parser = PythonParser(ctx)
    _, rels = parser.parse("m.py", b"class Base:\n    pass\nclass Child(Base):\n    pass")
    inherits = [r for r in rels if r.rel_type == RelationType.INHERITS]
    assert inherits
    assert inherits[0].target_id.endswith("m.py:Base")
    assert not inherits[0].target_id.startswith("unresolved:")


def test_python_relative_imports(ctx):
    parser = PythonParser(ctx)
    _, rels = parser.parse("pkg/mod.py", b"from . import sibling\nfrom .other import thing")
    imports = {r.target_id for r in rels if r.rel_type == RelationType.IMPORTS}
    assert "module:pkg.sibling" in imports
    assert "module:pkg.other" in imports


def test_python_relative_parent_import(ctx):
    parser = PythonParser(ctx)
    _, rels = parser.parse("x/y/z.py", b"from ..pkg.sub import a")
    imports = {r.target_id for r in rels if r.rel_type == RelationType.IMPORTS}
    assert "module:x.pkg.sub" in imports


def test_yaml_parser_kubernetes_object(ctx):
    parser = YamlParser(ctx)
    code = b"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: my-deploy"
    symbols, relationships = parser.parse("deploy.yaml", code)

    assert len(symbols) == 1
    assert symbols[0].symbol_type == SymbolType.RESOURCE
    assert symbols[0].name == "my-deploy"
    assert symbols[0].metadata["kind"] == "Deployment"

    assert len(relationships) == 1
    assert relationships[0].rel_type == RelationType.KUBERNETES_OBJECT


def test_terraform_parser_resource(ctx):
    parser = TerraformParser(ctx)
    code = b'resource "aws_instance" "web" { name = "web-server" }'
    symbols, relationships = parser.parse("main.tf", code)

    assert len(symbols) == 1
    assert symbols[0].symbol_type == SymbolType.RESOURCE
    assert symbols[0].name == "web"
    assert symbols[0].metadata["resource_type"] == "aws_instance"

    assert len(relationships) == 1
    assert relationships[0].rel_type == RelationType.CREATES


def test_terraform_parser_captures_all_block_types(ctx):
    parser = TerraformParser(ctx)
    code = b"""
variable "region" { default = "us-east-1" }
data "aws_ami" "ubuntu" { owners = ["099"] }
resource "aws_instance" "web" { ami = data.aws_ami.ubuntu.id }
module "vpc" { source = "./vpc" }
output "ip" { value = aws_instance.web.id }
locals { tag = var.region }
"""
    symbols, _ = parser.parse("main.tf", code)
    kinds = {s.metadata.get("tf_kind") for s in symbols}
    assert kinds == {"variable", "data", "resource", "module", "output", "local"}
    module = next(s for s in symbols if s.metadata.get("tf_kind") == "module")
    assert module.metadata["source"] == "./vpc"


def test_terraform_dependency_edges_resolve_across_symbols(ctx):
    from repo_intelligence.models.core import RepositoryModel
    from repo_intelligence.resolver import resolve_relationships

    parser = TerraformParser(ctx)
    code = b"""
variable "region" { default = "us-east-1" }
resource "aws_instance" "web" { region = var.region }
resource "aws_eip" "e" { instance = aws_instance.web.id }
"""
    symbols, relationships = parser.parse("main.tf", code)
    deps = [r for r in relationships if r.rel_type == RelationType.DEPENDS_ON]
    assert {r.target_id for r in deps} == {"tfaddr:var.region", "tfaddr:aws_instance.web"}

    model = resolve_relationships(
        RepositoryModel(repo_name="test-repo", root_path="/tmp", branch="main", commit="c",
                        symbols=symbols, relationships=relationships)
    )
    resolved = [
        r for r in model.relationships
        if r.rel_type == RelationType.DEPENDS_ON and not r.target_id.startswith("tfaddr:")
    ]
    assert len(resolved) == 2
    assert all(r.metadata.get("resolution_status") == "tf-resolved" for r in resolved)


def test_yaml_parser_crossplane_relationships(ctx):
    xrd = b"""apiVersion: apiextensions.crossplane.io/v1
kind: CompositeResourceDefinition
metadata:
  name: xwidgets.example.org
spec:
  group: example.org
  names:
    kind: XWidget
    plural: xwidgets
"""
    comp = b"""apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: xwidgets.example.org
spec:
  compositeTypeRef:
    apiVersion: example.org/v1
    kind: XWidget
  mode: Pipeline
  pipeline:
    - step: patch-and-transform
      functionRef:
        name: function-patch-and-transform
"""
    parser = YamlParser(ctx)
    xrd_symbols, xrd_rels = parser.parse("xrd.yaml", xrd)
    comp_symbols, comp_rels = parser.parse("composition.yaml", comp)

    xrd_to_type = [r for r in xrd_rels if r.rel_type == RelationType.DEFINES]
    assert xrd_to_type
    assert "XWidget" in xrd_to_type[0].target_id

    comp_to_type = [r for r in comp_rels if r.rel_type == RelationType.COMPOSITES]
    assert comp_to_type
    assert "XWidget" in comp_to_type[0].target_id

    comp_to_fn = [r for r in comp_rels if r.rel_type == RelationType.USES]
    assert comp_to_fn
    assert "function-patch-and-transform" in comp_to_fn[0].target_id


def test_go_parser_extracts_function_and_type(ctx):
    parser = GoParser(ctx)
    code = b"""package main

import "fmt"

type Server struct {
    name string
}

func (s *Server) Start() {
    fmt.Println("starting")
}

func main() {
    Start()
}
"""
    symbols, relationships = parser.parse("main.go", code)

    by_type = {s.symbol_type: s for s in symbols}
    assert SymbolType.CLASS in by_type
    assert by_type[SymbolType.CLASS].name == "Server"

    functions = [s for s in symbols if s.symbol_type == SymbolType.FUNCTION]
    methods = [s for s in symbols if s.symbol_type == SymbolType.METHOD]
    assert any(s.name == "main" for s in functions)
    assert any(s.name == "Start" for s in methods)

    method = next(s for s in methods if s.name == "Start")
    assert method.parent_id is not None
    assert "Server" in method.parent_id

    imports = [r for r in relationships if r.rel_type == RelationType.IMPORTS]
    assert any("fmt" in r.target_id for r in imports)


def test_go_parser_call_resolution(ctx):
    parser = GoParser(ctx)
    code = b"""package main

import "fmt"

func main() {
    fmt.Println("hello")
}
"""
    symbols, relationships = parser.parse("main.go", code)

    calls = [r for r in relationships if r.rel_type == RelationType.CALLS]
    assert len(calls) == 1
    assert "module:fmt.Println" in calls[0].target_id
