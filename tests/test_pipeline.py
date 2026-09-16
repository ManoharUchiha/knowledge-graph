import os
from unittest.mock import MagicMock

from repo_intelligence.config import Config
from repo_intelligence.scanner.discovery import RepositoryScanner
from repo_intelligence.parsers.factory import ParserFactory
from repo_intelligence.parsers.base import ParserContext
from repo_intelligence.models.core import RepositoryModel, Symbol, SymbolType, SourceLocation, make_file_id
from repo_intelligence.resolver import resolve_relationships
from repo_intelligence.graph.client import Neo4jClient
from repo_intelligence.graph.builder import GraphBuilder


def test_indexing_pipeline(tmp_path):
    # 1. Setup synthetic repo
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    src_dir = repo_dir / "src"
    src_dir.mkdir()

    main_py = src_dir / "main.py"
    main_py.write_text("def main():\n    print('hello')")

    # 2. Mock Neo4j Client
    mock_client = MagicMock(spec=Neo4jClient)

    # 3. Run pipeline
    config = Config(str(repo_dir))
    scanner = RepositoryScanner(config)
    files = scanner.scan()

    context = ParserContext(
        repo_name="test-repo",
        root_path=str(repo_dir),
        branch="main",
        commit="abc1234",
    )

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
    builder = GraphBuilder(mock_client)
    builder.build(model)

    # 4. Verify
    assert len(model.symbols) > 0
    assert mock_client.execute_query.called


def test_resolver_resolves_local_module_call(tmp_path):
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    services_dir = repo_dir / "services"
    services_dir.mkdir()
    (services_dir / "order.py").write_text("def create_order(): pass")

    main_py = repo_dir / "main.py"
    main_py.write_text("from services.order import create_order\n\ndef main():\n    create_order()")

    context = ParserContext(
        repo_name="test-repo",
        root_path=str(repo_dir),
        branch="main",
        commit="abc1234",
    )

    model = RepositoryModel(
        repo_name=context.repo_name,
        root_path=context.root_path,
        branch=context.branch,
        commit=context.commit,
    )

    for f in RepositoryScanner(Config(str(repo_dir))).scan():
        parser = ParserFactory.get_parser(f.language, context)
        with open(os.path.join(repo_dir, f.path), "rb") as src:
            symbols, rels = parser.parse(f.path, src.read())
            model.symbols.extend(symbols)
            model.relationships.extend(rels)

    model = resolve_relationships(model)

    calls = [r for r in model.relationships if r.rel_type.name == "CALLS"]
    assert any(not c.target_id.startswith("unresolved:") for c in calls)
