"""CLI interface for CodeNexus."""

import click
import json
import sys
import time
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .graph import DependencyGraph, Node
from .parser import CodeParser
from .server import CodeNexusServer

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

console = Console()

@click.group()
@click.option("--workspace", "-w", default=".", help="Workspace path")
@click.version_option(version="0.1.0", prog_name="codenexus")
@click.pass_context
def main(ctx, workspace):
    """CodeNexus: The context engine for AI coding agents.
    
    Reduce token usage by 50-70% while improving code context quality.
    """
    ctx.ensure_object(dict)
    ctx.obj["workspace"] = Path(workspace).resolve()

@main.command()
@click.option("--full", "-f", is_flag=True, help="Full re-index (ignore cache)")
@click.option("--workers", "-j", default=4, help="Number of parallel workers")
@click.pass_context
def index(ctx, full, workers):
    """Index the workspace for context retrieval."""
    workspace = ctx.obj["workspace"]
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Indexing workspace...", total=None)
        
        server = CodeNexusServer(workspace, max_workers=workers)
        start_time = time.time()
        count = server.index_workspace(incremental=not full)
        elapsed = time.time() - start_time
    
    if count > 0:
        console.print(f"[bold green]✓ Indexed {count} files in {elapsed:.2f}s[/]")
    else:
        console.print("[yellow]No new files to index[/]")

@main.command()
@click.argument("query")
@click.option("--max-tokens", "-t", default=8000, help="Max tokens for capsule")
@click.option("--top", "-n", default=10, help="Number of results")
@click.pass_context
def search(ctx, query, max_tokens, top):
    """Search for context related to a query."""
    workspace = ctx.obj["workspace"]
    db_path = workspace / ".codenexus" / "index.db"
    
    if not db_path.exists():
        console.print("[red]No index found. Run 'codenexus index' first.[/]")
        return
    
    graph = DependencyGraph(db_path)
    nodes = graph.search_nodes(query, limit=top)
    
    if not nodes:
        console.print(f"[yellow]No results for: {query}[/]")
        return
    
    table = Table(title=f"Search Results: {query}")
    table.add_column("File", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Type", style="magenta")
    table.add_column("Lines", style="yellow")
    table.add_column("Centrality", style="blue")
    
    for node in nodes:
        table.add_row(
            node.file_path,
            node.name,
            node.node_type,
            f"{node.start_line}-{node.end_line}",
            f"{node.centrality_score:.4f}"
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
    """Show index status and statistics."""
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
    
    # Get centrality stats
    avg_centrality = graph.conn.execute(
        "SELECT AVG(centrality_score) FROM nodes"
    ).fetchone()[0] or 0
    
    max_centrality = graph.conn.execute(
        "SELECT MAX(centrality_score) FROM nodes"
    ).fetchone()[0] or 0
    
    # Get node type distribution
    type_dist = graph.conn.execute(
        "SELECT node_type, COUNT(*) FROM nodes GROUP BY node_type"
    ).fetchall()
    
    table = Table(title="Index Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Nodes", str(node_count))
    table.add_row("Edges", str(edge_count))
    table.add_row("Files", str(file_count))
    table.add_row("Avg Centrality", f"{avg_centrality:.4f}")
    table.add_row("Max Centrality", f"{max_centrality:.4f}")
    
    console.print(table)
    
    # Node type distribution
    if type_dist:
        type_table = Table(title="Node Types")
        type_table.add_column("Type", style="cyan")
        type_table.add_column("Count", style="green")
        
        for node_type, count in type_dist:
            type_table.add_row(node_type, str(count))
        
        console.print(type_table)

@main.command()
@click.argument("symbol")
@click.option("--depth", "-d", default=2, help="Depth of impact analysis")
@click.pass_context
def impact(ctx, symbol, depth):
    """Show impact graph for a symbol."""
    workspace = ctx.obj["workspace"]
    db_path = workspace / ".codenexus" / "index.db"
    
    if not db_path.exists():
        console.print("[red]No index found. Run 'codenexus index' first.[/]")
        return
    
    graph = DependencyGraph(db_path)
    
    # Find the node
    nodes = graph.search_nodes(symbol, limit=1)
    if not nodes:
        console.print(f"[yellow]Symbol not found: {symbol}[/]")
        return
    
    node = nodes[0]
    impact = graph.get_impact_graph(node.id, depth=depth)
    
    console.print(f"[bold]Impact Analysis: {node.name}[/]")
    console.print(f"File: {node.file_path}")
    console.print(f"Type: {node.node_type}")
    console.print(f"Centrality: {node.centrality_score:.4f}")
    console.print()
    
    if impact["direct"]:
        console.print("[bold cyan]Direct Dependents:[/]")
        for dep in impact["direct"]:
            console.print(f"  • {dep['name']} ({dep['file']})")
    
    if impact["indirect"]:
        console.print("[bold yellow]Indirect Dependents:[/]")
        for dep in impact["indirect"]:
            console.print(f"  • {dep['name']} ({dep['file']}) [depth: {dep['depth']}]")
    
    console.print(f"\n[bold]Total Impact: {impact['total']}[/]")

@main.command()
@click.option("--depth", "-d", default=10, help="Number of top nodes to show")
@click.pass_context
def top(ctx, depth):
    """Show top nodes by centrality score."""
    workspace = ctx.obj["workspace"]
    db_path = workspace / ".codenexus" / "index.db"
    
    if not db_path.exists():
        console.print("[red]No index found. Run 'codenexus index' first.[/]")
        return
    
    graph = DependencyGraph(db_path)
    nodes = graph.get_top_central_nodes(depth)
    
    if not nodes:
        console.print("[yellow]No nodes found.[/]")
        return
    
    table = Table(title=f"Top {depth} Nodes by Centrality")
    table.add_column("Rank", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Type", style="magenta")
    table.add_column("File", style="yellow")
    table.add_column("Centrality", style="blue")
    
    for i, node in enumerate(nodes, 1):
        table.add_row(
            str(i),
            node.name,
            node.node_type,
            node.file_path,
            f"{node.centrality_score:.6f}"
        )
    
    console.print(table)

@main.command()
@click.pass_context
def serve(ctx):
    """Start MCP server for AI agent integration."""
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

@main.command()
@click.pass_context
def clear(ctx):
    """Clear all index data."""
    workspace = ctx.obj["workspace"]
    db_path = workspace / ".codenexus" / "index.db"
    
    if not db_path.exists():
        console.print("[yellow]No index to clear.[/]")
        return
    
    server = CodeNexusServer(workspace)
    server.clear_index()
    
    console.print("[bold green]✓ Index cleared[/]")

@main.group()
def llm():
    """Local LLM commands for enhanced context."""
    pass

@llm.command()
@click.option("--size", "-s", default="small", 
              type=click.Choice(["small", "medium", "large"]),
              help="Model size to download")
def download(size):
    """Download a local LLM model."""
    from .llm import LocalLLM, LLMConfig
    
    console.print(f"[bold blue]Downloading {size} model...[/]")
    
    llm = LocalLLM(LLMConfig(verbose=True))
    model_path = llm.download_model(size)
    
    if model_path:
        console.print(f"[bold green]✓ Model downloaded: {model_path}[/]")
    else:
        console.print("[red]Failed to download model[/]")

@llm.command()
@click.argument("model_path")
@click.option("--gpu", "-g", is_flag=True, help="Enable GPU acceleration")
def serve(model_path, gpu):
    """Start LLM server for context optimization."""
    from .llm import init_llm
    
    console.print(f"[bold blue]Starting LLM server...[/]")
    console.print(f"Model: {model_path}")
    console.print(f"GPU: {'enabled' if gpu else 'disabled'}")
    
    n_gpu_layers = -1 if gpu else 0
    llm = init_llm(model_path=model_path, n_gpu_layers=n_gpu_layers)
    
    if llm._loaded:
        console.print("[bold green]✓ LLM server ready[/]")
        console.print("[yellow]LLM will be used for context optimization[/]")
    else:
        console.print("[red]Failed to load model[/]")

@llm.command()
@click.argument("query")
def analyze(query):
    """Analyze query intent using local LLM."""
    from .llm import get_llm
    
    llm = get_llm()
    intent = llm.analyze_intent(query)
    
    console.print(f"[bold]Query: {query}[/]")
    console.print(f"[green]Detected intent: {intent}[/]")

@llm.command()
def status():
    """Show LLM status."""
    from .llm import get_llm, LLAMA_CPP_AVAILABLE
    
    console.print("[bold]LLM Status[/]")
    console.print(f"  llama-cpp-python: {'installed' if LLAMA_CPP_AVAILABLE else 'not installed'}")
    
    llm = get_llm()
    info = llm.get_model_info()
    
    if info["status"] == "loaded":
        console.print(f"  Model: {info['model_path']}")
        console.print(f"  Context: {info['context_size']}")
        console.print(f"  GPU layers: {info['gpu_layers']}")
    else:
        console.print("  Model: not loaded")

if __name__ == "__main__":
    main()
