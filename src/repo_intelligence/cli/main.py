import os
import click
from repo_intelligence.config import Config, config as global_config
from repo_intelligence.git.repository import GitRepository
from repo_intelligence.scanner.discovery import RepositoryScanner
from repo_intelligence.parsers.factory import ParserFactory
from repo_intelligence.parsers.base import ParserContext
from repo_intelligence.models.core import RepositoryModel, Symbol, SymbolType, SourceLocation, make_file_id
from repo_intelligence.resolver import resolve_relationships
from repo_intelligence.semantic.factory import SemanticResolverFactory
from repo_intelligence.graph.client import Neo4jClient
from repo_intelligence.graph.builder import GraphBuilder
from repo_intelligence.graph.queries import GraphQueries


@click.group()
@click.option('--neo4j-uri', default="bolt://localhost:7687", help="Neo4j URI")
@click.option('--neo4j-user', default="neo4j", help="Neo4j User")
@click.option('--neo4j-password', default="password", help="Neo4j Password")
def cli(neo4j_uri, neo4j_user, neo4j_password):
    """Repository Intelligence CLI"""
    click.get_current_context().obj = {
        "client": Neo4jClient(neo4j_uri, neo4j_user, neo4j_password),
    }


@cli.command()
@click.argument('repo_path', type=click.Path(exists=True))
@click.option('--semantic', is_flag=True, help="Run semantic resolution backends")
@click.option('--semantic-backend', default="jedi", help="Semantic resolver to use (jedi, scip, lsp, joern)")
@click.option('--clear', is_flag=True, help="Remove previously indexed data for this repo before re-indexing")
@click.pass_context
def index(ctx, repo_path, semantic, semantic_backend, clear):
    """Index the repository at the given path."""
    client = ctx.obj["client"]

    import repo_intelligence.config
    repo_intelligence.config.config = Config(repo_path)

    from repo_intelligence.config import config as cfg

    git_repo = GitRepository(repo_path)
    git_info = git_repo.get_info()

    context = ParserContext(
        repo_name=git_info.repo_name,
        root_path=git_info.root_path,
        branch=git_info.branch,
        commit=git_info.commit,
    )

    if clear:
        _clear_repo(ctx.obj["client"], git_info.repo_name)

    scanner = RepositoryScanner(cfg)
    files = scanner.scan()
    click.echo(f"Scanning {repo_path}... Found {len(files)} files.")

    model = RepositoryModel(
        repo_name=context.repo_name,
        root_path=context.root_path,
        branch=context.branch,
        commit=context.commit,
        files=files,
    )

    # Create File symbols for every discovered file so graph relationships can link to them.
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

    for f in files:
        try:
            parser = ParserFactory.get_parser(f.language, context)
            abs_path = os.path.join(repo_path, f.path)
            with open(abs_path, "rb") as source_file:
                symbols, relationships = parser.parse(f.path, source_file.read())
                model.symbols.extend(symbols)
                model.relationships.extend(relationships)
        except ValueError as e:
            if "Unsupported language" not in str(e):
                click.echo(f"Error parsing {f.path}: {e}", err=True)
        except Exception as e:
            click.echo(f"Error parsing {f.path}: {e}", err=True)

    model = resolve_relationships(model)

    if semantic:
        resolver = SemanticResolverFactory.get_resolver(semantic_backend)
        if resolver:
            click.echo(f"Running semantic resolution: {resolver.name} ...")
            model = resolver.resolve(model, repo_path)
        else:
            click.echo(
                f"Unknown semantic backend '{semantic_backend}'. Available: "
                f"{', '.join(SemanticResolverFactory.available_resolvers())}",
                err=True,
            )

    builder = GraphBuilder(client)
    builder.build(model)
    click.echo(
        f"Indexing complete for {context.repo_name}@{context.branch} ({context.commit[:8]}). "
        f"Symbols: {len(model.symbols)}, Relationships: {len(model.relationships)}."
    )


@cli.command()
@click.argument('name')
@click.option('--repo', help="Filter by repository name")
@click.option('--branch', help="Filter by branch")
@click.pass_context
def find_symbol(ctx, name, repo, branch):
    """Find a symbol by name."""
    queries = GraphQueries(ctx.obj["client"])
    results = queries.find_symbol(name, repo=repo, branch=branch)
    if not results:
        click.echo("No symbols found with that name.")
        return
    for r in results:
        click.echo(
            f"{r['id']} | {r['type']} | {r.get('file_path', '')}"
        )


@cli.command()
@click.argument('symbol_id')
@click.pass_context
def get_callers(ctx, symbol_id):
    """Get callers of a symbol."""
    queries = GraphQueries(ctx.obj["client"])
    results = queries.get_callers(symbol_id)
    if not results:
        click.echo("No callers found.")
        return
    for r in results:
        click.echo(
            f"{r['id']} ({r.get('type', '')}) in {r.get('file_path', '')}:{r.get('line', '')} "
            f"[confidence={r.get('confidence', '')}]"
        )


@cli.command()
@click.argument('symbol_id')
@click.pass_context
def get_callees(ctx, symbol_id):
    """Get callees of a symbol."""
    queries = GraphQueries(ctx.obj["client"])
    results = queries.get_callees(symbol_id)
    if not results:
        click.echo("No callees found.")
        return
    for r in results:
        click.echo(
            f"{r['id']} ({r.get('type', '')}) in {r.get('file_path', '')}:{r.get('line', '')} "
            f"[confidence={r.get('confidence', '')}]"
        )


@cli.command()
@click.argument('file_id')
@click.pass_context
def get_imports(ctx, file_id):
    """Get imports for a file (use the file symbol id)."""
    queries = GraphQueries(ctx.obj["client"])
    results = queries.get_imports(file_id)
    if not results:
        click.echo("No imports found.")
        return
    for r in results:
        click.echo(f"{r['id']} ({r.get('type', '')})")


@cli.command()
@click.argument('module_id')
@click.pass_context
def get_importers(ctx, module_id):
    """Get files that import a module symbol id."""
    queries = GraphQueries(ctx.obj["client"])
    results = queries.get_importers(module_id)
    if not results:
        click.echo("No importers found.")
        return
    for r in results:
        click.echo(f"{r['id']} ({r['path']})")


@cli.command()
@click.argument('start_id')
@click.option('--depth', default=10, help="Maximum traversal depth")
@click.option('--max-paths', default=20, help="Maximum paths to return")
@click.pass_context
def trace(ctx, start_id, depth, max_paths):
    """Trace execution flow starting from a symbol id."""
    queries = GraphQueries(ctx.obj["client"])
    paths = queries.trace_execution_flow(start_id, depth=depth, max_paths=max_paths)
    if not paths:
        click.echo("No execution paths found.")
        return
    for i, record in enumerate(paths, 1):
        p = record.get("p")
        if p:
            # .data() serializes paths as alternating node dicts and relationship strings.
            node_ids = [
                item.get("id", "?") for item in p if isinstance(item, dict)
            ]
            click.echo(f"Path {i}: {' -> '.join(node_ids)}")


@cli.command()
@click.argument('path')
@click.option('--repo', help="Filter by repository name")
@click.option('--branch', help="Filter by branch")
@click.pass_context
def find_file(ctx, path, repo, branch):
    """Find a file by relative path."""
    queries = GraphQueries(ctx.obj["client"])
    results = queries.find_file(path, repo=repo, branch=branch)
    if not results:
        click.echo("No file found.")
        return
    for r in results:
        click.echo(r['id'])


@cli.command("list-symbols")
@click.option('--type', 'symbol_type', help="Filter by symbol type (function, class, resource, file)")
@click.option('--repo', help="Filter by repository name")
@click.option('--branch', help="Filter by branch")
@click.pass_context
def list_symbols(ctx, symbol_type, repo, branch):
    """List symbols in the graph."""
    queries = GraphQueries(ctx.obj["client"])
    results = queries.list_symbols(symbol_type=symbol_type, repo=repo, branch=branch)
    if not results:
        click.echo("No symbols found.")
        return
    for r in results:
        click.echo(
            f"{r['id']} | {r['type']} | {r.get('file_path', '')}"
        )


@cli.command("list-resources")
@click.option('--repo', help="Filter by repository name")
@click.option('--branch', help="Filter by branch")
@click.pass_context
def list_resources(ctx, repo, branch):
    """List Kubernetes and Terraform resources."""
    queries = GraphQueries(ctx.obj["client"])
    results = queries.list_symbols(symbol_type="resource", repo=repo, branch=branch)
    if not results:
        click.echo("No resources found.")
        return
    for r in results:
        kind = r.get("metadata", {}).get("kind") or r.get("metadata", {}).get("resource_type")
        click.echo(f"{kind or 'resource'}: {r['name']} ({r['file_path']})")


@cli.command("list-repos")
@click.pass_context
def list_repos(ctx):
    """List repositories currently indexed in the graph."""
    queries = GraphQueries(ctx.obj["client"])
    results = queries.list_repositories()
    if not results:
        click.echo("No repositories indexed.")
        return
    for r in results:
        click.echo(
            f"{r['name']} | {r['branch']} | {r['commit'][:8] if r.get('commit') else 'unknown'} "
            f"| {r.get('root_path', '')}"
        )


@cli.command("find-xrd")
@click.argument('kind')
@click.option('--repo', help="Filter by repository name")
@click.pass_context
def find_xrd(ctx, kind, repo):
    """Find CompositeResourceDefinitions that define the given XR kind."""
    queries = GraphQueries(ctx.obj["client"])
    results = queries.find_xrd_for_kind(kind, repo=repo)
    if not results:
        click.echo(f"No XRD found for kind {kind}.")
        return
    for r in results:
        click.echo(f"{r['name']} ({r['file_path']}) [{r.get('repo', '')}]")


@cli.command("find-compositions")
@click.argument('kind')
@click.option('--repo', help="Filter by repository name")
@click.pass_context
def find_compositions(ctx, kind, repo):
    """Find Compositions that target the given XR kind."""
    queries = GraphQueries(ctx.obj["client"])
    results = queries.find_compositions_for_kind(kind, repo=repo)
    if not results:
        click.echo(f"No compositions found for kind {kind}.")
        return
    for r in results:
        click.echo(f"{r['name']} ({r['file_path']})")


@cli.command("composition-functions")
@click.argument('composition_id')
@click.pass_context
def composition_functions(ctx, composition_id):
    """List function references used by a Composition."""
    queries = GraphQueries(ctx.obj["client"])
    results = queries.get_functions_for_composition(composition_id)
    if not results:
        click.echo("No functions found for that composition.")
        return
    for r in results:
        click.echo(f"{r['name']} ({r.get('type', '')})")


@cli.command("explain")
@click.argument('file_path')
@click.option('--repo', help="Filter by repository name")
@click.option('--format', 'output_format', type=click.Choice(['text', 'json']), default='text', help="Output format")
@click.pass_context
def explain(ctx, file_path, repo, output_format):
    """Explain how a file is implemented (symbols, Crossplane chain, Python refs)."""
    import json as _json

    queries = GraphQueries(ctx.obj["client"])
    result = queries.explain_file(file_path, repo=repo)
    if "error" in result:
        click.echo(result["error"], err=True)
        return

    if output_format == "json":
        click.echo(_json.dumps(result, indent=2, default=str))
        return

    click.echo(f"File: {result['file']['file_name']}")
    click.echo(
        f"Summary: {result['summary']['resources']} resources, "
        f"{result['summary']['classes']} classes, "
        f"{result['summary']['functions']} functions"
    )

    cp = result.get("crossplane") or {}
    if cp.get("xrds"):
        click.echo("\nXRDs defining this XR kind:")
        for xrd in cp["xrds"]:
            click.echo(f"  - {xrd['name']} ({xrd['file_path']})")
    if cp.get("compositions"):
        click.echo("\nCompositions implementing this XR kind:")
        for comp in cp["compositions"]:
            click.echo(f"  - {comp['name']} ({comp['file_path']})")
    if cp.get("composition_functions"):
        click.echo("\nComposition pipeline functions:")
        for fn in cp["composition_functions"]:
            click.echo(f"  - {fn['name']}")

    py = result.get("python") or {}
    for label, items in [
        ("Callers", py.get("callers")),
        ("Callees", py.get("callees")),
        ("Imports", py.get("imports")),
        ("Inherits", py.get("inherits")),
    ]:
        if items:
            click.echo(f"\n{label}:")
            for item in items:
                click.echo(f"  - {item['name']} ({item.get('file_path', '')})")


def _clear_repo(client, repo_name: str) -> None:
    """Delete all graph data for a repository name."""
    click.echo(f"Clearing existing data for repository '{repo_name}'...")
    client.execute_write(
        "MATCH (s:Symbol) WHERE s.repo = $repo_name DETACH DELETE s",
        {"repo_name": repo_name},
    )
    client.execute_write(
        "MATCH (r:Repository) WHERE r.name = $repo_name DETACH DELETE r",
        {"repo_name": repo_name},
    )
    click.echo("Cleared.")


if __name__ == "__main__":
    cli()
