import os
from repo_intelligence.config import Config
from repo_intelligence.scanner.discovery import RepositoryScanner
from repo_intelligence.parsers.factory import ParserFactory
from repo_intelligence.parsers.base import ParserContext
from repo_intelligence.models.core import RepositoryModel, Symbol, SymbolType, SourceLocation, make_file_id
from repo_intelligence.resolver import resolve_relationships
from repo_intelligence.semantic.jedi_resolver import JediResolver


def test_jedi_resolver_resolves_inheritance(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    base_py = repo_dir / "base.py"
    base_py.write_text("class Base:\n    def run(self): pass\n")

    child_py = repo_dir / "child.py"
    child_py.write_text("from base import Base\n\nclass Child(Base):\n    pass\n")

    context = ParserContext(
        repo_name="repo",
        root_path=str(repo_dir),
        branch="main",
        commit="abc",
    )

    config = Config(str(repo_dir))
    scanner = RepositoryScanner(config)
    files = scanner.scan()

    model = RepositoryModel(
        repo_name=context.repo_name,
        root_path=context.root_path,
        branch=context.branch,
        commit=context.commit,
    )

    for f in files:
        file_id = make_file_id(context.repo_name, context.branch, f.path)
        model.symbols.append(
            Symbol(
                id=file_id,
                repo=context.repo_name,
                branch=context.branch,
                commit=context.commit,
                name=f.path,
                symbol_type=SymbolType.FILE,
                location=SourceLocation(
                    file_path=f.path,
                    start_line=1,
                    start_col=0,
                    end_line=1,
                    end_col=0,
                ),
                metadata={"language": f.language, "size": f.size},
            )
        )
        parser = ParserFactory.get_parser(f.language, context)
        with open(os.path.join(repo_dir, f.path), "rb") as src:
            symbols, rels = parser.parse(f.path, src.read())
            model.symbols.extend(symbols)
            model.relationships.extend(rels)

    model = resolve_relationships(model)

    resolver = JediResolver()
    model = resolver.resolve(model, str(repo_dir))

    resolved_inherits = [
        r for r in model.relationships
        if r.rel_type.name == "INHERITS" and not r.target_id.startswith("unresolved:")
    ]
    assert resolved_inherits

    # The Child class should inherit from Base (resolved statically via the
    # import, and confirmed/kept resolved by the jedi resolver).
    child_base = [r for r in resolved_inherits if "Child" in r.source_id and "Base" in r.target_id]
    assert child_base
