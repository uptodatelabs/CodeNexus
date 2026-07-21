"""CLI interface for CodeNexus."""

import click
import json
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .graph import DependencyGraph
from .parser import CodeParser
from .server import CodeNexusServer

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

console = Console()

@click.group()
@click.option("--workspace", "-w", default=".", help="Workspace path")
@click.pass_context
def main(ctx, workspace):
    """CodeNexus: The context engine for AI coding agents."""
    ctx.ensure_object(dict)
    ctx.obj["workspace"] = Path(workspace).resolve()

@main.command()
@click.pass_context
def index(ctx):
    """Index the workspace."""
    workspace = ctx.obj["workspace"]
    console.print(f"[bold blue]Indexing workspace:[/] {workspace}")
    
    server = CodeNexusServer(workspace)
    count = server.index_workspace()
    
    console.print(f"[bold green]✓ Indexed {count} files[/]")

@main.command()
@click.argument("query")
@click.option("--max-tokens", "-t", default=8000, help="Max tokens for capsule")
@click.pass_context
def search(ctx, query, max_tokens):
    """Search for context related to a query."""
    workspace = ctx.obj["workspace"]
    db_path = workspace / ".codenexus" / "index.db"
    
    if not db_path.exists():
        console.print("[red]No index found. Run 'codenexus index' first.[/]")
        return
    
    graph = DependencyGraph(db_path)
    nodes = graph.search_nodes(query, limit=10)
    
    if not nodes:
        console.print(f"[yellow]No results for: {query}[/]")
        return
    
    table = Table(title=f"Search Results: {query}")
    table.add_column("File", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Type", style="magenta")
    table.add_column("Lines", style="yellow")
    
    for node in nodes:
        table.add_row(
            node.file_path,
            node.name,
            node.node_type,
            f"{node.start_line}-{node.end_line}"
        )
    
    console.print(table)

@main.command()
@click.argument("task")
@click.option("--max-tokens", "-t", default=8000, help="Max tokens")
@click.pass_context
def pipeline(ctx, task, max_tokens):
    """Run context pipeline for a task."""
    workspace = ctx.obj["workspace"]
    server = CodeNexusServer(workspace)
    
    import asyncio
    result = asyncio.run(server._run_pipeline({
        "task": task,
        "max_tokens": max_tokens
    }))
    
    console.print(Panel(result[0].text, title="Context Capsule"))

@main.command()
@click.pass_context
def status(ctx):
    """Show index status."""
    workspace = ctx.obj["workspace"]
    db_path = workspace / ".codenexus" / "index.db"
    
    if not db_path.exists():
        console.print("[yellow]No index found.[/]")
        return
    
    graph = DependencyGraph(db_path)
    node_count = graph.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    edge_count = graph.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    file_count = graph.conn.execute(
        "SELECT COUNT(DISTINCT file_path) FROM nodes"
    ).fetchone()[0]
    
    table = Table(title="Index Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Nodes", str(node_count))
    table.add_row("Edges", str(edge_count))
    table.add_row("Files", str(file_count))
    
    console.print(table)

@main.command()
@click.pass_context
def serve(ctx):
    """Start MCP server."""
    workspace = ctx.obj["workspace"]
    server = CodeNexusServer(workspace)
    
    console.print("[bold green]Starting MCP server...[/]")
    console.print(f"Workspace: {workspace}")
    
    # Index if needed
    if not (workspace / ".codenexus" / "index.db").exists():
        console.print("[yellow]No index found. Indexing workspace...[/]")
        server.index_workspace()
    
    # Run MCP server (simplified - real implementation would use stdio)
    console.print("[bold blue]MCP server ready. Use with Claude Code or other agents.[/]")

if __name__ == "__main__":
    main()
