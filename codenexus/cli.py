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
from .license import get_license, LicenseTier

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

console = Console()

@click.group()
@click.option("--workspace", "-w", default=".", help="Workspace path")
@click.version_option(version="1.1.14", prog_name="codenexus")
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
        _task = progress.add_task("[cyan]Indexing workspace...", total=None)
        
        server = CodeNexusServer(workspace, max_workers=workers)
        start_time = time.time()
        count = server.index_workspace(incremental=not full)
        elapsed = time.time() - start_time
    
    if count > 0:
        console.print(f"[bold green]Indexed {count} files in {elapsed:.2f}s[/]")
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
    
    table = Table(title="Index Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Nodes", str(node_count))
    table.add_row("Edges", str(edge_count))
    table.add_row("Files", str(file_count))
    
    console.print(table)

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
            console.print(f"  - {dep['name']} ({dep['file']})")
    
    if impact["indirect"]:
        console.print("[bold yellow]Indirect Dependents:[/]")
        for dep in impact["indirect"]:
            console.print(f"  - {dep['name']} ({dep['file']}) [depth: {dep['depth']}]")
    
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
    
    # Auto-index if not exists
    db_path = workspace / ".codenexus" / "index.db"
    if not db_path.exists():
        print(f"Indexing workspace: {workspace}", file=sys.stderr)
        from .server import CodeNexusServer
        server = CodeNexusServer(workspace)
        count = server.index_workspace()
        print(f"Indexed {count} files", file=sys.stderr)
    
    # Run MCP server via stdio
    from .mcp_server import CodeNexusMCPServer
    mcp_server = CodeNexusMCPServer(str(workspace))
    mcp_server.run()

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
    
    console.print("[green]Index cleared[/]")

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
    
    llm = LocalLLM(LLMConfig(verbose=True))
    model_path = llm.download_model(size)
    
    if model_path:
        console.print(f"[green]Model downloaded: {model_path}[/]")
    else:
        console.print("[red]Failed to download model[/]")

@llm.command()
@click.argument("model_path")
@click.option("--gpu", "-g", is_flag=True, help="Enable GPU acceleration")
def serve(model_path, gpu):
    """Start LLM server for context optimization."""
    from .llm import init_llm
    
    console.print(f"[blue]Starting LLM server...[/]")
    console.print(f"Model: {model_path}")
    console.print(f"GPU: {'enabled' if gpu else 'disabled'}")
    
    n_gpu_layers = -1 if gpu else 0
    llm = init_llm(model_path=model_path, n_gpu_layers=n_gpu_layers)
    
    if llm._loaded:
        console.print("[green]LLM server ready[/]")
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
    from .llm import LLAMA_CPP_AVAILABLE, get_llm
    
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

@main.group()
def workspace():
    """Multi-repo workspace commands."""
    pass

@workspace.command()
@click.argument("name")
def init(name):
    """Initialize a new workspace."""
    from .workspace import MultiRepoWorkspace, WorkspaceConfig
    
    workspace_path = Path.cwd()
    ws = MultiRepoWorkspace(workspace_path)
    ws.config = WorkspaceConfig(name=name)
    ws.save_config()
    
    console.print(f"[green]Workspace '{name}' initialized[/]")
    console.print(f"Config: {ws.config_path}")

@workspace.command()
@click.argument("alias")
@click.argument("path", type=click.Path(exists=True))
@click.option("--description", "-d", default="", help="Repository description")
def add(alias, path, description):
    """Add a repository to the workspace."""
    from .workspace import MultiRepoWorkspace
    
    workspace_path = Path.cwd()
    ws = MultiRepoWorkspace(workspace_path)
    
    if ws.add_repo(alias, Path(path), description):
        console.print(f"[green]Repository '{alias}' added[/]")
    else:
        console.print(f"[red]Failed to add repository '{alias}'[/]")

@workspace.command()
@click.argument("alias")
def remove(alias):
    """Remove a repository from the workspace."""
    from .workspace import MultiRepoWorkspace
    
    workspace_path = Path.cwd()
    ws = MultiRepoWorkspace(workspace_path)
    
    if ws.remove_repo(alias):
        console.print(f"[green]Repository '{alias}' removed[/]")
    else:
        console.print(f"[red]Failed to remove repository '{alias}'[/]")

@workspace.command()
@click.option("--repo", "-r", help="Specific repo to index (default: all)")
def index(repo):
    """Index all repositories in the workspace."""
    from .workspace import MultiRepoWorkspace
    
    workspace_path = Path.cwd()
    ws = MultiRepoWorkspace(workspace_path)
    
    if not ws.config:
        console.print("[red]No workspace found. Run 'codenexus workspace init' first.[/]")
        return
    
    console.print(f"[blue]Indexing workspace: {ws.config.name}[/]")
    
    if repo:
        count = ws.index_repo(repo)
        console.print(f"  {repo}: {count} files")
    else:
        results = ws.index_all()
        for alias, count in results.items():
            console.print(f"  {alias}: {count} files")
    
    console.print("[green]Indexing complete[/]")

@workspace.command()
@click.argument("query")
@click.option("--repos", "-r", multiple=True, help="Specific repos to search")
@click.option("--limit", "-l", default=10, help="Max results per repo")
def search(query, repos, limit):
    """Search across repositories."""
    from .workspace import MultiRepoWorkspace
    
    workspace_path = Path.cwd()
    ws = MultiRepoWorkspace(workspace_path)
    
    if not ws.config:
        console.print("[red]No workspace found. Run 'codenexus workspace init' first.[/]")
        return
    
    repo_list = list(repos) if repos else None
    results = ws.search(query, repos=repo_list, limit=limit)
    
    if not results:
        console.print(f"[yellow]No results for: {query}[/]")
        return
    
    table = Table(title=f"Cross-repo Search: {query}")
    table.add_column("Repo", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Type", style="magenta")
    table.add_column("File", style="yellow")
    table.add_column("Score", style="blue")
    
    for result in results:
        node = result["node"]
        table.add_row(
            result["repo"],
            node.name,
            node.node_type,
            node.file_path,
            f"{result['score']:.4f}"
        )
    
    console.print(table)

@workspace.command()
def status():
    """Show workspace status."""
    from .workspace import MultiRepoWorkspace
    
    workspace_path = Path.cwd()
    ws = MultiRepoWorkspace(workspace_path)
    
    if not ws.config:
        console.print("[yellow]No workspace found.[/]")
        return
    
    info = ws.get_status()
    
    console.print(f"[bold]Workspace: {info['name']}[/]")
    console.print(f"Repositories: {info['repos']}")
    console.print()
    
    if info['repo_status']:
        table = Table(title="Repository Status")
        table.add_column("Alias", style="cyan")
        table.add_column("Path", style="green")
        table.add_column("Nodes", style="yellow")
        
        for repo in info['repo_status']:
            table.add_row(
                repo['alias'],
                repo['path'],
                str(repo['nodes'])
            )
        
        console.print(table)

@workspace.command()
def deps():
    """Show cross-repo dependencies."""
    from .workspace import MultiRepoWorkspace
    
    workspace_path = Path.cwd()
    ws = MultiRepoWorkspace(workspace_path)
    
    if not ws.config:
        console.print("[yellow]No workspace found.[/]")
        return
    
    deps = ws.get_cross_repo_dependencies()
    
    console.print("[bold]Cross-repo Dependencies[/]")
    console.print()
    
    for repo, dep_list in deps.items():
        if dep_list:
            console.print(f"[cyan]{repo}[/] depends on:")
            for dep in dep_list:
                console.print(f"  -> {dep}")
        else:
            console.print(f"[cyan]{repo}[/]: no dependencies")

@main.group()
def memory():
    """Session memory and decision tracking."""
    pass

@memory.command()
@click.argument("name")
def start(name):
    """Start a new session."""
    from .memory import get_memory
    
    mem = get_memory()
    session = mem.create_session(name)
    
    console.print(f"[green]Session started: {session.id}[/]")
    console.print(f"Name: {session.name}")

@memory.command()
@click.argument("session_id")
@click.option("--summary", "-s", default="", help="Session summary")
def end(session_id, summary):
    """End a session."""
    from .memory import get_memory
    
    mem = get_memory()
    mem.end_session(session_id, summary)
    
    if not summary:
        summary = mem.generate_session_summary(session_id)
        console.print("[bold]Session Summary:[/]")
        console.print(summary)
    
    console.print(f"[green]Session ended: {session_id}[/]")

@memory.command()
@click.argument("session_id")
@click.argument("description")
@click.option("--type", "-t", "decision_type", 
              type=click.Choice(["code_change", "architecture", "bug_fix", 
                                 "refactor", "feature", "config"]),
              default="code_change",
              help="Decision type")
@click.option("--rationale", "-r", default="", help="Decision rationale")
@click.option("--files", "-f", multiple=True, help="Files affected")
@click.option("--tags", multiple=True, help="Tags")
def decide(session_id, description, decision_type, rationale, files, tags):
    """Record a decision."""
    from .memory import get_memory, DecisionType
    
    mem = get_memory()
    decision = mem.add_decision(
        session_id,
        DecisionType(decision_type),
        description,
        rationale,
        list(files),
        list(tags)
    )
    
    console.print(f"[green]Decision recorded: {decision.id}[/]")
    console.print(f"Type: {decision_type}")
    console.print(f"Description: {description}")

@memory.command()
@click.argument("session_id")
@click.option("--limit", "-l", default=10, help="Number of recent sessions")
def sessions(limit):
    """List recent sessions."""
    from .memory import get_memory
    
    mem = get_memory()
    sessions = mem.get_recent_sessions(limit)
    
    if not sessions:
        console.print("[yellow]No sessions found.[/]")
        return
    
    table = Table(title="Recent Sessions")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Start", style="yellow")
    table.add_column("End", style="magenta")
    
    for s in sessions:
        table.add_row(
            s.id,
            s.name,
            s.start_time.strftime("%Y-%m-%d %H:%M"),
            s.end_time.strftime("%Y-%m-%d %H:%M") if s.end_time else "ongoing"
        )
    
    console.print(table)

@memory.command()
@click.argument("session_id")
def decisions(session_id):
    """List decisions in a session."""
    from .memory import get_memory
    
    mem = get_memory()
    decisions = mem.get_decisions(session_id)
    
    if not decisions:
        console.print("[yellow]No decisions found.[/]")
        return
    
    table = Table(title=f"Decisions in Session: {session_id}")
    table.add_column("Type", style="cyan")
    table.add_column("Description", style="green")
    table.add_column("Files", style="yellow")
    
    for d in decisions:
        table.add_row(
            d.decision_type.value,
            d.description[:50] + "..." if len(d.description) > 50 else d.description,
            str(len(d.files_affected))
        )
    
    console.print(table)

@memory.command()
@click.argument("query")
def search(query):
    """Search memories and decisions."""
    from .memory import get_memory
    
    mem = get_memory()
    
    decisions = mem.search_decisions(query)
    memories = mem.search_memories(query)
    
    if not decisions and not memories:
        console.print(f"[yellow]No results for: {query}[/]")
        return
    
    if decisions:
        console.print("[bold]Decisions:[/]")
        for d in decisions[:5]:
            console.print(f"  [{d.decision_type.value}] {d.description}")
    
    if memories:
        console.print("[bold]Memories:[/]")
        for m in memories[:5]:
            console.print(f"  {m['key']}: {m['value'][:50]}...")

@memory.command()
def stats():
    """Show memory statistics."""
    from .memory import get_memory
    
    mem = get_memory()
    stats = mem.get_statistics()
    
    table = Table(title="Memory Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Sessions", str(stats["sessions"]))
    table.add_row("Decisions", str(stats["decisions"]))
    table.add_row("Memories", str(stats["memories"]))
    table.add_row("File Changes", str(stats["file_changes"]))
    
    console.print(table)
    
    if stats["decision_types"]:
        type_table = Table(title="Decision Types")
        type_table.add_column("Type", style="cyan")
        type_table.add_column("Count", style="green")
        
        for dtype, count in stats["decision_types"].items():
            type_table.add_row(dtype, str(count))
        
        console.print(type_table)

@memory.command()
@click.argument("session_id")
def summary(session_id):
    """Generate session summary."""
    from .memory import get_memory
    
    mem = get_memory()
    summary = mem.generate_session_summary(session_id)
    
    if not summary:
        console.print(f"[yellow]Session not found: {session_id}[/]")
        return
    
    console.print(Panel(summary, title="Session Summary"))

@main.group()
def license():
    """License management commands."""
    pass

@license.command()
def status():
    """Show license status."""
    from .license import get_license
    
    lic = get_license()
    info = lic.get_license_info()
    
    table = Table(title="License Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Tier", info["tier"])
    table.add_row("Owner", info["owner"] or "N/A")
    table.add_row("Expires", info["expires_at"] or "Never")
    table.add_row("Valid", "Yes" if info["is_valid"] else "No")
    
    console.print(table)

@license.command()
@click.argument("license_key")
def activate(license_key):
    """Activate a license key."""
    from .license import get_license
    
    lic = get_license()
    
    if lic.activate_license(license_key):
        console.print("[green]License activated successfully[/]")
        info = lic.get_license_info()
        console.print(f"Tier: {info['tier']}")
        console.print(f"Expires: {info['expires_at']}")
    else:
        console.print("[red]Failed to activate license[/]")
        console.print("Please check your license key and try again.")

@license.command()
def features():
    """Show available features."""
    from .license import get_license
    
    lic = get_license()
    tier = lic.get_tier()
    
    console.print(f"[bold]Current Tier: {tier.value}[/]")
    console.print()
    
    features = [
        ("Basic parsing (3 languages)", True),
        ("Full parsing (9 languages)", lic.has_feature("languages")),
        ("Local LLM", lic.has_feature("llm")),
        ("Multi-repo", lic.has_feature("multi_repo")),
        ("Session memory", lic.has_feature("memory")),
        ("VS Code extension", lic.has_feature("vscode_extension")),
        ("CLI", lic.has_feature("cli")),
        ("Priority support", lic.has_feature("priority_support")),
    ]
    
    table = Table(title="Features")
    table.add_column("Feature", style="cyan")
    table.add_column("Status", style="green")
    
    for feature, available in features:
        status = "Yes" if available else "No (Pro)"
        table.add_row(feature, status)
    
    console.print(table)

@license.command()
def upgrade():
    """Show upgrade information."""
    console.print("[bold]Upgrade to CodeNexus Pro[/]")
    console.print()
    console.print("Pro features:")
    console.print("  - All 9 languages")
    console.print("  - Local LLM support")
    console.print("  - Multi-repo workspaces")
    console.print("  - Session memory")
    console.print("  - Priority support")
    console.print()
    console.print("Pricing:")
    console.print("  - Monthly: $19/month")
    console.print("  - Annual: $190/year (save 17%)")
    console.print()
    console.print("Purchase at: https://codenexus.dev/pricing")

@main.group()
def wizard():
    """AI agent setup wizard."""
    pass

@wizard.command()
def detect():
    """Detect installed AI coding agents."""
    from .wizard import AgentWizard
    
    wiz = AgentWizard()
    wiz.print_detected_agents()

@wizard.command()
def list():
    """List all supported AI agents."""
    from .wizard import AGENTS
    
    table = Table(title="Supported AI Agents")
    table.add_column("Name", style="cyan")
    table.add_column("MCP", style="green")
    table.add_column("Description")
    
    for agent_type, info in AGENTS.items():
        mcp = "Yes" if info.mcp_support else "No"
        table.add_row(info.name, mcp, info.description)
    
    console.print(table)

@wizard.command()
@click.argument("agent_name")
@click.option("--project", "-p", default=".", help="Project path")
def setup(agent_name, project):
    """Setup a specific AI agent."""
    from .wizard import AgentWizard, get_agent_by_name
    
    agent_type = get_agent_by_name(agent_name)
    if not agent_type:
        console.print(f"[red]Unknown agent: {agent_name}[/]")
        console.print("[dim]Use 'codenexus wizard list' to see supported agents[/]")
        return
    
    wiz = AgentWizard()
    wiz.print_setup_guide(agent_type, Path(project).resolve())
    
    # Ask to apply
    apply = input("\nApply configuration and index project? (y/n): ").strip().lower()
    if apply == "y" or apply == "yes":
        console.print("\n[yellow]Applying configuration...[/]")
        success = wiz.apply_config(agent_type, Path(project).resolve())
        if success:
            console.print("[green]Configuration applied and project indexed![/]")
        else:
            console.print("[red]Failed to apply configuration[/]")

@wizard.command()
def interactive():
    """Run interactive setup wizard."""
    from .wizard import AgentWizard
    
    wiz = AgentWizard()
    wiz.interactive_setup()

@wizard.command()
def clear():
    """Clear index data with interactive selection."""
    from pathlib import Path
    import shutil
    
    # Find all .codenexus directories
    search_paths = [
        Path.home() / ".codenexus",
        Path.cwd() / ".codenexus",
    ]
    
    # Also search common project locations
    home = Path.home()
    for item in home.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            codenexus_dir = item / ".codenexus"
            if codenexus_dir.exists():
                search_paths.append(codenexus_dir)
    
    # Find unique .codenexus directories
    index_dirs = []
    seen = set()
    
    for path in search_paths:
        if path.exists() and path.is_dir():
            real_path = path.resolve()
            if real_path not in seen:
                seen.add(real_path)
                index_dirs.append(path)
    
    if not index_dirs:
        console.print("[yellow]No CodeNexus index directories found.[/]")
        return
    
    # Display list
    console.print("[bold]Found CodeNexus index directories:[/]\n")
    
    table = Table(title="Index Directories")
    table.add_column("#", style="cyan")
    table.add_column("Path", style="green")
    table.add_column("Size", style="yellow")
    
    for i, dir_path in enumerate(index_dirs, 1):
        # Calculate size
        total_size = 0
        for f in dir_path.rglob("*"):
            if f.is_file():
                total_size += f.stat().st_size
        
        size_str = f"{total_size / 1024:.1f} KB" if total_size < 1024 * 1024 else f"{total_size / (1024*1024):.1f} MB"
        table.add_row(str(i), str(dir_path), size_str)
    
    console.print(table)
    
    # Ask for selection
    console.print("\n[bold]Options:[/]")
    console.print("  - Enter numbers separated by comma (e.g., 1,3)")
    console.print("  - Enter 'all' to clear all")
    console.print("  - Enter 'q' to cancel")
    
    selection = input("\nSelect directories to clear: ").strip()
    
    if selection.lower() == 'q':
        console.print("[yellow]Cancelled.[/]")
        return
    
    if selection.lower() == 'all':
        selected_indices = list(range(len(index_dirs)))
    else:
        try:
            selected_indices = [int(x.strip()) - 1 for x in selection.split(",")]
        except ValueError:
            console.print("[red]Invalid input.[/]")
            return
    
    # Validate indices
    valid_indices = [i for i in selected_indices if 0 <= i < len(index_dirs)]
    
    if not valid_indices:
        console.print("[red]No valid selections.[/]")
        return
    
    # Confirm
    console.print(f"\n[bold]About to clear {len(valid_indices)} index(es):[/]")
    for i in valid_indices:
        console.print(f"  - {index_dirs[i]}")
    
    confirm = input("\nConfirm? (y/n): ").strip().lower()
    if confirm != 'y' and confirm != 'yes':
        console.print("[yellow]Cancelled.[/]")
        return
    
    # Clear selected directories
    cleared = 0
    for i in valid_indices:
        try:
            shutil.rmtree(index_dirs[i])
            console.print(f"[green]Cleared: {index_dirs[i]}[/]")
            cleared += 1
        except Exception as e:
            console.print(f"[red]Failed to clear {index_dirs[i]}: {e}[/]")
    
    console.print(f"\n[bold green]Cleared {cleared} index(es)[/]")

if __name__ == "__main__":
    main()
