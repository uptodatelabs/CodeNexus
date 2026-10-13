"""CodeNexus TUI — keyboard-first interface (Textual based).

Design goal: no free-text typing required. All actions reachable via the
arrow keys + Enter; settings toggled with space; escape returns to the
dashboard. The plain CLI (`codenexus ...`) remains fully supported.

Screens:
  Dashboard  — index stats + action menu (re-index / browse / pipeline / settings / quit)
  Search     — indexed symbol table; Enter opens the impact view
  Impact     — direct/indirect dependents of a symbol
  Pipeline   — pick a pivot symbol; shows context capsule + token estimate
  Settings   — toggle options; persisted to <workspace>/.codenexus/ui_config.json
  Manage     — index lifecycle: incremental re-index / full rebuild / delete
  Wizard     — keyboard-only agent setup wizard (agent -> mode -> MCP config)
  Memory     — recent session-memory sessions
  Workspace  — multi-repo workspace registration status
  Llm        — local LLM (llama-cpp-python) availability and model status
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import (
    DataTable,
    DirectoryTree,
    Footer,
    Header,
    Input,
    OptionList,
    Static,
)
from textual.widgets.option_list import Option

from .graph import DependencyGraph
from .llm import get_llm
from .memory import DecisionType, SessionMemory
from .server import CodeNexusServer
from .wizard import AGENTS, AgentWizard
from .workspace import MultiRepoWorkspace, WorkspaceConfig

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover - defensive, mirrors cli.py
        pass

_CONFIG_PATH = "ui_config.json"

_DEFAULT_UI_CONFIG: dict = {
    "memory_enabled": True,
    "llm_enabled": False,
    "max_tokens": 8000,
    "search_limit": 10,
    "impact_depth": 2,
}

_SETTING_KEYS = (
    "memory_enabled",
    "llm_enabled",
    "max_tokens",
    "search_limit",
    "impact_depth",
)

_BOOLEAN_KEYS = ("memory_enabled", "llm_enabled")

_CYCLE_PRESETS = {
    "max_tokens": [4000, 8000, 16000, 32000, 64000],
    "search_limit": [10, 25, 50, 100],
    "impact_depth": [1, 2, 3, 5],
}

_SETTING_PROMPTS = {
    "memory_enabled": "Session memory (decisions, summaries): {}",
    "llm_enabled": "Local LLM post-processing: {}",
    "max_tokens": "Pipeline token budget: {}",
    "search_limit": "Search result limit: {}",
    "impact_depth": "Impact analysis depth: {}",
}


def _setting_prompt(key: str, value) -> str:
    if key in _BOOLEAN_KEYS:
        shown = "ON" if value else "OFF"
    else:
        shown = value
    return _SETTING_PROMPTS[key].format(shown)


def _ui_config_path(ws: Path) -> Path:
    return ws / ".codenexus" / _CONFIG_PATH


def _load_ui_config(ws: Path) -> dict:
    path = _ui_config_path(ws)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {**_DEFAULT_UI_CONFIG, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_DEFAULT_UI_CONFIG)


def _save_ui_config(ws: Path, config: dict) -> None:
    path = _ui_config_path(ws)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _shorten(path: str, limit: int = 48) -> str:
    home = str(Path.home())
    if path.startswith(home):
        path = "~" + path[len(home):]
    if len(path) > limit:
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        if len(parts) > 3:
            path = "/".join(parts[:2] + ["…"] + parts[-2:])
    return path


def _list_drives() -> list[str]:
    """Enumerate available drive letters (Windows) / root (POSIX)."""
    if sys.platform != "win32":
        return ["/"] if Path("/").exists() else []
    return [
        f"{chr(o)}:"
        for o in range(ord("A"), ord("Z") + 1)
        if Path(f"{chr(o)}:\\").exists()
    ]


class NavScreen(Screen):
    """Base screen: escape pops back to the previous screen.

    Actions bound on a screen resolve in the *screen's* namespace, so
    `action_back` must live here (not on the App) for Esc to work.
    """

    BINDINGS = [("escape", "back", "Back")]

    def action_back(self) -> None:
        # Stack: [_default, dashboard, ...deeper]. Dashboard must not pop
        # onto the blank `_default` screen.
        if len(self.app.screen_stack) > 2:
            self.app.pop_screen()


class DashboardScreen(NavScreen):
    """Landing screen: index stats + keyboard action menu."""

    BINDINGS = [("escape", "back", "Back/QA")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="dash-body"):
            with Vertical(id="dash-left"):
                yield Static("", id="stats")
            with Vertical(id="dash-right"):
                yield OptionList(id="menu")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_stats()
        menu = self.query_one("#menu", OptionList)
        if menu.option_count == 0:
            menu.add_options(
                [
                    Option("Re-index workspace", id="reindex"),
                    Option("Browse & search symbols", id="search"),
                    Option("Context pipeline (pick a symbol)", id="pipeline"),
                    Option("Settings", id="settings"),
                    Option("Index management", id="manage"),
                    Option("Agent wizard", id="wizard"),
                    Option("Session memory", id="memory"),
                    Option("Multi-repo workspace", id="workspace"),
                    Option("Local LLM status", id="llm"),
                    Option("Index status", id="status"),
                    Option("Index list", id="indexlist"),
                    Option("Top symbols", id="top"),
                    Option("MCP serve command", id="serve"),
                    Option("License", id="license"),
                    Option("Help", id="help"),
                    Option("Quit", id="quit"),
                ]
            )
        menu.focus()

    def _refresh_stats(self) -> None:
        try:
            stats = self.app.workspace_stats()
            text = (
                f"[b]Workspace[/b] {_shorten(str(self.app.workspace))}\n"
                f"[b]Nodes[/b] {stats['nodes']}  [b]Edges[/b] {stats['edges']}\n"
                f"[b]Files indexed[/b] {stats['files']}\n\n"
                f"Version {self.app.version}\n"
                f"[dim]Navigation: ↑/↓ + Enter · Esc = back[/dim]"
            )
        except FileNotFoundError:
            text = (
                "[b]Workspace[/b] " + _shorten(str(self.app.workspace)) + "\n"
                "[yellow]No index yet — pick 'Re-index workspace'.[/yellow]\n"
                f"Version {self.app.version}"
            )
        self.query_one("#stats", Static).update(text)

    @on(OptionList.OptionSelected, "#menu")
    def _menu_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option_id
        if option_id == "reindex":
            self._do_reindex()
        elif option_id == "search":
            self.app.push_screen("search")
        elif option_id == "pipeline":
            self.app.push_screen("pipeline")
        elif option_id == "settings":
            self.app.push_screen("settings")
        elif option_id == "manage":
            self.app.push_screen("manage")
        elif option_id == "wizard":
            self.app.push_screen("wizard")
        elif option_id == "memory":
            self.app.push_screen("memory")
        elif option_id == "workspace":
            self.app.push_screen("workspace")
        elif option_id == "llm":
            self.app.push_screen("llm")
        elif option_id == "status":
            self.app.push_screen("status")
        elif option_id == "indexlist":
            # Push a fresh instance: screens resolved from SCREENS are cached
            # singletons and would keep their first on_mount content (a stale
            # "No index found" after reindexing in a later session).
            self.app.push_screen(IndexListScreen())
        elif option_id == "top":
            self.app.push_screen("top")
        elif option_id == "serve":
            self.app.push_screen("serve")
        elif option_id == "license":
            self.app.push_screen("license")
        elif option_id == "help":
            self.app.push_screen(HelpScreen())
        elif option_id == "quit":
            self.app.exit()

    def _do_reindex(self) -> None:
        server = CodeNexusServer(self.app.workspace)
        count = server.index_workspace(incremental=False)
        self.query_one("#stats", Static).update(
            f"[green]Indexed {count} files.[/green]\n" + self._stats_body()
        )

    def _stats_body(self) -> str:
        stats = self.app.workspace_stats()
        return (
            f"[b]Nodes[/b] {stats['nodes']}  [b]Edges[/b] {stats['edges']}\n"
            f"[b]Files indexed[/b] {stats['files']}"
        )

    def refresh_stats(self) -> None:
        self._refresh_stats()


class SearchScreen(NavScreen):
    """Browse every indexed symbol; Enter -> impact view."""

    BINDINGS = [("escape", "back", "Back")]
    COLUMNS = ("Name", "Type", "File", "Centrality")

    def compose(self) -> ComposeResult:
        yield Static("[b]Symbols (↑/↓ navigate · Enter = impact · Esc = back)[/b]", id="search-hint")
        yield DataTable(id="symbols")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#symbols", DataTable)
        for name, key in zip(self.COLUMNS, ("name", "type", "file", "centrality"), strict=True):
            table.add_column(name, key=key)
        table.cursor_type = "row"  # Enter must emit RowSelected (default "cell" emits CellSelected)
        graph = DependencyGraph(self.app.workspace / ".codenexus" / "index.db")
        try:
            nodes = graph.get_top_central_nodes(self.app.ui_config["search_limit"] * 5)
        finally:
            graph.close()
        for node in nodes:
            table.add_row(
                node.name,
                node.node_type,
                _shorten(node.file_path),
                f"{node.centrality_score:.6f}",
                key=node.id,
            )
        if table.row_count:
            table.focus()

    @on(DataTable.RowSelected, "#symbols")
    def _row_selected(self, event: DataTable.RowSelected) -> None:
        self.app.selected_symbol = event.row_key.value
        self.app.push_screen("impact")


class ImpactScreen(NavScreen):
    """Impact analysis for the symbol selected in SearchScreen."""

    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Static("", id="impact-view")
        yield Footer()

    def on_mount(self) -> None:
        node_id = self.app.selected_symbol
        graph = DependencyGraph(self.app.workspace / ".codenexus" / "index.db")
        try:
            impacted = graph.get_impact_graph(
                node_id, depth=int(self.app.ui_config.get("impact_depth", 2))
            )
        finally:
            graph.close()
        lines = [f"[b]Impact analysis[/b] for node id: {node_id}"]
        direct = impacted.get("direct", [])
        indirect = impacted.get("indirect", [])
        lines.append(f"[b]Direct dependents[/b] ({len(direct)}):")
        for dep in direct[:20]:
            lines.append(f"  • {dep['name']}  {_shorten(dep['file'])}")
        lines.append(f"[b]Indirect dependents[/b] ({len(indirect)}):")
        for dep in indirect[:20]:
            lines.append(f"  • {dep['name']}  [dim]depth {dep['depth']}[/dim]")
        lines.append(f"[b]Total impact[/b]: {impacted.get('total', 0)}")
        self.query_one("#impact-view", Static).update("\n".join(lines))


class PipelineScreen(NavScreen):
    """Pick a symbol; render the context capsule produced by the pipeline."""

    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Static("[b]Pick a pivot symbol for the context capsule[/b]", id="pipeline-hint")
        yield OptionList(id="pipeline-options")
        yield Static("", id="pipeline-view")
        yield Footer()

    def on_mount(self) -> None:
        options = self.query_one("#pipeline-options", OptionList)
        graph = DependencyGraph(self.app.workspace / ".codenexus" / "index.db")
        try:
            nodes = graph.get_top_central_nodes(25)
        finally:
            graph.close()
        self._pipeline_nodes = nodes
        if nodes:
            options.add_options(
                [Option(f"{n.name}  ({n.node_type})  {_shorten(n.file_path)}", id=n.id) for n in nodes]
            )
            options.focus()
        else:
            self.query_one("#pipeline-view", Static).update("[yellow]No indexed symbols.[/yellow]")

    @on(OptionList.OptionSelected, "#pipeline-options")
    def _option_selected(self, event: OptionList.OptionSelected) -> None:
        node_id = event.option_id
        node = next((n for n in self._pipeline_nodes if n.id == node_id), None)
        server = CodeNexusServer(self.app.workspace)
        task = (
            f"Understand and modify {node.name} ({node.node_type}) in "
            f"{node.file_path}" if node else "Understand the hottest symbols"
        )
        data = server._pipeline_data(
            {"task": task, "max_tokens": self.app.ui_config["max_tokens"]}
        )
        lines = [
            f"[b]Task:[/] {task}",
            f"[b]Intent:[/] {data.get('intent', '-')}",
            f"[b]Token estimate:[/] {data.get('token_estimate', 0)}",
            "",
            f"[b]Pivot files[/b]: {len(data.get('pivot_files', []))}",
            f"[b]Skeletons[/b]: {len(data.get('skeletons', []))}",
        ]
        for pf in data.get("pivot_files", [])[:10]:
            lines.append(f"  • {pf.get('name', '?')}  {_shorten(pf.get('path', ''))}")
        for sk in data.get("skeletons", [])[:10]:
            lines.append(f"  ◦ {sk.get('name', '?')}  {_shorten(sk.get('path', ''))}")
        self.query_one("#pipeline-view", Static).update("\n".join(lines))


class ManageScreen(NavScreen):
    """Index management: rebuild / delete the index — keyboard only."""

    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Static("[b]Index management[/b]", id="manage-hint")
        yield OptionList(id="manage-list")
        yield Static("", id="manage-info")
        yield Footer()

    def on_mount(self) -> None:
        options = self.query_one("#manage-list", OptionList)
        options.add_options(
            [
                Option("Rebuild index (full re-index)", id="rebuild"),
                Option("Delete index (clear all data)", id="clear"),
            ]
        )
        self._update_info()
        options.focus()

    def _stats_line(self) -> str:
        try:
            stats = self.app.workspace_stats()
            return (
                f"{stats['nodes']} nodes · {stats['edges']} edges · "
                f"{stats['files']} files indexed"
            )
        except FileNotFoundError:
            return "No index found"

    def _update_info(self, note: str = "") -> None:
        text = f"[b]Status[/b] {self._stats_line()}"
        if note:
            text = f"{note}\n{text}"
        self.query_one("#manage-info", Static).update(text)

    @on(OptionList.OptionSelected, "#manage-list")
    def _selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id == "rebuild":
            server = CodeNexusServer(self.app.workspace)
            count = server.index_workspace(incremental=False)
            self._update_info(f"[green]Rebuilt index: {count} files.[/green]")
        elif event.option_id == "clear":
            server = CodeNexusServer(self.app.workspace)
            server.clear_index()
            self._update_info("[green]Index deleted.[/green]")


class _WizardDirTree(DirectoryTree):
    """DirectoryTree whose Enter *chooses* the highlighted entry.

    The stock DirectoryTree expands a directory on Enter; the wizard needs
    Enter to apply the directory, so the enter binding is replaced.
    """

    BINDINGS = [
        ("enter", "pick", "Pick directory"),
        ("backspace", "up_dir", "Go up one directory"),
        ("left", "up_dir", "Go up one directory"),
        ("right", "down_dir", "Descend one directory"),
    ]

    class DriveSelectionRequested(Message):
        """Posted when going up from the drive root: offer a drive picker."""

    def action_pick(self) -> None:
        node = self.cursor_node
        if node is not None and node.data is not None:
            self.post_message(DirectoryTree.FileSelected(node, node.data.path))

    def action_up_dir(self) -> None:
        """Move the browse root one level up so the whole filesystem is
        reachable from a workspace-rooted tree (drive root = end)."""
        current = Path(self.path)
        parent = current.parent
        if current == Path(current.anchor) or parent == current:
            # Already at the filesystem/drive root — offer drive selection.
            self.post_message(self.DriveSelectionRequested())
            return
        self.path = str(parent)
        self.reload()

    def action_down_dir(self) -> None:
        """Descend into the highlighted directory (Right arrow)."""
        node = self.cursor_node
        if node is None or node.data is None:
            return
        raw = getattr(node.data, "path", None)
        if not raw:
            return
        target = Path(raw)
        if not target.is_dir():
            return
        self.path = str(target)
        self.reload()
        self.cursor_line = 0


class WizardScreen(NavScreen):
    """Agent setup wizard — pick agent + mode from lists, MCP config shown.

    Keyboard-only mirror of `codenexus wizard`: the agent list and the setup
    modes are selectable options, and the resulting MCP config block is
    rendered for reading. Nothing needs to be typed.
    """

    BINDINGS = [("escape", "back", "Back")]

    MODES = [
        ("Single project (global index)", "single"),
        ("Multi-repo workspace (one registration)", "multi"),
        ("Per-project local scope (independent index)", "project"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("[b]Agent setup wizard — choose an agent[/b]", id="wizard-hint")
        yield OptionList(id="wizard-list")
        yield Input(id="wizard-input", placeholder="Type a directory path…")
        yield _WizardDirTree(self.app.workspace, id="wizard-tree")
        yield OptionList(id="drive-list")
        yield Static("", id="wizard-view")
        yield Footer()

    def on_mount(self) -> None:
        options = self.query_one("#wizard-list", OptionList)
        wizard = AgentWizard()
        installed = wizard.detect_installed_agents()
        agent_types = installed or list(AGENTS.keys())
        if installed:
            self.query_one("#wizard-hint", Static).update(
                f"[b]Agent setup wizard — {len(installed)} agent(s) detected"
                " (↑/↓ · Enter) · Esc = back[/b]"
            )
        else:
            self.query_one("#wizard-hint", Static).update(
                "[b]Agent setup wizard —[/b] no agents detected; "
                "[yellow]showing all supported agents[/yellow]"
            )
        options.add_options(
            [Option(f"{AGENTS[t].name} — {AGENTS[t].description}", id=t.value) for t in agent_types]
        )
        self._stage = "agent"
        self._agent_types = agent_types
        options.focus()

    @on(OptionList.OptionSelected, "#wizard-list")
    def _selected(self, event: OptionList.OptionSelected) -> None:
        options = self.query_one("#wizard-list", OptionList)
        if self._stage == "agent":
            self._chosen_type = next(
                t for t in self._agent_types if t.value == event.option_id
            )
            options.clear_options()
            options.add_options(
                [Option(label, id=mode_id) for label, mode_id in self.MODES]
            )
            self._stage = "mode"
            self.query_one("#wizard-hint", Static).update(
                f"[b]Setup mode for {AGENTS[self._chosen_type].name}[/b]"
            )
        elif self._stage == "mode":
            # Directory stage: pick from candidates, browse, or enter manually.
            self._stage = "dir"
            options.clear_options()
            self._add_dir_options(options)
        elif self._stage == "dir":
            if event.option_id == "__manual__":
                inp = self.query_one("#wizard-input", Input)
                inp.display = True
                inp.focus()
                self._stage = "manual"
            elif event.option_id == "__browse__":
                self._open_browse(options)
            else:
                self._apply_directory(Path(event.option_id))

    @on(Input.Submitted, "#wizard-input")
    def _manual_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip().strip('"')
        target = Path(raw).expanduser()
        if not target.is_dir():
            self.query_one("#wizard-view", Static).update(
                f"[red]Directory not found:[/] {raw}"
            )
            return  # stay in manual stage so the user can correct the path
        self.query_one("#wizard-input", Input).display = False
        self._apply_directory(target)

    def _apply_directory(self, target: Path) -> None:
        wizard = AgentWizard()
        info = AGENTS[self._chosen_type]
        config = wizard.generate_mcp_config(self._chosen_type, target)
        lines = [f"[b]{info.name}[/b] — project directory: {target}"]
        lines.append("```json")
        lines.append(json.dumps(config, indent=2))
        lines.append("```")
        lines.append("")
        lines.append(
            f"CLI command: {wizard.generate_cli_command(self._chosen_type, target)}"
        )
        self.query_one("#wizard-view", Static).update("\n".join(lines))
        self._stage = "dir"
        self.query_one("#wizard-input", Input).display = False
        tree = self.query_one("#wizard-tree", _WizardDirTree)
        if tree.display:
            tree.display = False
        self.query_one("#wizard-list", OptionList).display = True
        self.app.ui_config["wizard_project_path"] = str(target)
        _save_ui_config(self.app.workspace, self.app.ui_config)

    def _add_dir_options(self, options: OptionList) -> None:
        candidates = [self.app.workspace, Path.home()]
        opts = [
            Option(f"{_shorten(str(p))}  (directory)", id=str(p))
            for p in candidates
        ]
        opts.append(Option("Browse the filesystem…", id="__browse__"))
        opts.append(Option("Enter a directory manually…", id="__manual__"))
        options.add_options(opts)
        self.query_one("#wizard-hint", Static).update(
            "[b]Choose the project directory[/b] (↑/↓ · Enter) · Esc = back"
        )

    def _restore_dir_menu(self) -> None:
        self._stage = "dir"
        self.query_one("#drive-list", OptionList).display = False
        options = self.query_one("#wizard-list", OptionList)
        options.display = True
        options.clear_options()
        self._add_dir_options(options)
        options.focus()

    def _open_browse(self, options: OptionList) -> None:
        options.display = False
        tree = self.query_one("#wizard-tree", _WizardDirTree)
        tree.path = str(self.app.workspace)
        tree.reload()
        tree.cursor_line = 0
        tree.display = True
        tree.focus()
        self._stage = "browse"
        self.query_one("#drive-list", OptionList).display = False
        self.query_one("#wizard-hint", Static).update(
            "[b]Browse directories[/b] — ↑/↓ move · ← up · → descend · "
            "Enter = select · Esc = back"
        )

    @on(_WizardDirTree.DriveSelectionRequested)
    def _offer_drive_selection(self) -> None:
        drives = _list_drives()
        if not drives:
            return  # no drives discovered — keep the tree as-is
        drive_list = self.query_one("#drive-list", OptionList)
        drive_list.clear_options()
        drive_list.add_options([Option(f"{d}\\  (drive)", id=d) for d in drives])
        tree = self.query_one("#wizard-tree", _WizardDirTree)
        tree.display = False
        drive_list.display = True
        drive_list.focus()

    @on(OptionList.OptionSelected, "#drive-list")
    def _drive_selected(self, event: OptionList.OptionSelected) -> None:
        drive = str(event.option_id)
        self.query_one("#drive-list", OptionList).display = False
        tree = self.query_one("#wizard-tree", _WizardDirTree)
        tree.path = str(Path(drive + "\\"))
        tree.reload()
        tree.cursor_line = 0
        tree.display = True
        tree.focus()

    @on(DirectoryTree.FileSelected)
    def _dir_tree_selected(self, event: DirectoryTree.FileSelected) -> None:
        self._apply_directory(Path(event.path))

    def action_back(self) -> None:
        if self._stage == "browse":
            self.query_one("#wizard-tree", _WizardDirTree).display = False
            self._restore_dir_menu()
        elif self._stage == "manual":
            self.query_one("#wizard-input", Input).display = False
            self._restore_dir_menu()
        else:
            super().action_back()


class MemoryScreen(NavScreen):
    """Recent session memory entries — keyboard read-only view."""

    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Static("[b]Session memory — recent sessions[/b]", id="memory-hint")
        yield OptionList(id="memory-actions")
        yield Input(id="memory-input", placeholder="Search query…")
        yield Static("", id="memory-view")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#memory-input", Input).display = False
        acts = self.query_one("#memory-actions", OptionList)
        if acts.option_count == 0:
            acts.add_options([
                    Option("Start session", id="mem-start"),
                    Option("End latest session", id="mem-end"),
                    Option("Record decision", id="mem-decide"),
                    Option("List sessions", id="mem-sessions"),
                    Option("List decisions (latest session)", id="mem-decisions"),
                    Option("Show statistics", id="mem-stats"),
                    Option("Search decisions", id="mem-search"),
                    Option("Latest summary", id="mem-summary"),
            ])
        view = self.query_one("#memory-view", Static)
        db = self.app.workspace / ".codenexus" / "memory.db"
        mem = SessionMemory(db)
        try:
            sessions = mem.get_recent_sessions(limit=10)
        finally:
            mem.close()
        if not sessions:
            view.update("[yellow]No sessions recorded yet.[/yellow]")
            return
        lines = [
            f"  • {s.name}  [dim]{s.start_time:%Y-%m-%d %H:%M}[/dim]"
            for s in sessions
        ]
        view.update("\n".join(lines))


    @on(OptionList.OptionSelected, "#memory-actions")
    def _memory_action(self, event: OptionList.OptionSelected) -> None:
        view = self.query_one("#memory-view", Static)
        db = self.app.workspace / ".codenexus" / "memory.db"
        mem = SessionMemory(db)
        try:
            if event.option_id == "mem-start":
                s = mem.create_session("tui-session")
                view.update("Session started: " + s.name)
            elif event.option_id == "mem-end":
                recent = mem.get_recent_sessions(limit=1)
                if not recent:
                    view.update("No sessions to end")
                else:
                    mem.end_session(recent[0].id, "")
                    view.update("Session ended: " + recent[0].name)
            elif event.option_id == "mem-decide":
                recent = mem.get_recent_sessions(limit=1)
                if not recent:
                    view.update("No session — start one first")
                else:
                    d = mem.add_decision(
                        recent[0].id,
                        DecisionType.CODE_CHANGE,
                        "TUI decision",
                        "Recorded from TUI",
                    )
                    view.update("Decision recorded: " + d.id)
            elif event.option_id == "mem-sessions":
                recent = mem.get_recent_sessions(limit=10)
                if not recent:
                    view.update("No sessions")
                else:
                    view.update("\n".join("  - " + s.name for s in recent))
            elif event.option_id == "mem-decisions":
                recent = mem.get_recent_sessions(limit=1)
                if not recent:
                    view.update("No sessions")
                else:
                    decs = mem.get_decisions(recent[0].id)
                    if not decs:
                        view.update("No decisions in latest session")
                    else:
                        view.update("\n".join(f"  - [{d.decision_type.value}] {d.description[:60]}" for d in decs[:10]))
            elif event.option_id == "mem-stats":
                st = mem.get_statistics()
                view.update("Sessions: " + str(st.get("sessions", 0)) + " Decisions: " + str(st.get("decisions", 0)))
            elif event.option_id == "mem-search":
                inp = self.query_one("#memory-input", Input)
                inp.display = True
                inp.focus()
                view.update("Type query then Enter to search decisions/memories")
            elif event.option_id == "mem-summary":
                recent = mem.get_recent_sessions(limit=1)
                if not recent:
                    view.update("No sessions")
                else:
                    summ = mem.generate_session_summary(recent[0].id)
                    view.update(summ or "No summary")
        finally:
            mem.close()


    @on(Input.Submitted, "#memory-input")
    def _mem_input_submitted(self, event: Input.Submitted) -> None:
        q = event.value.strip()
        view = self.query_one("#memory-view", Static)
        db = self.app.workspace / ".codenexus" / "memory.db"
        mem = SessionMemory(db)
        try:
            decs = mem.search_decisions(q, limit=10)
            mems = mem.search_memories(q, limit=10)
            if not decs and not mems:
                view.update("No results for: " + q)
            else:
                lines = []
                for d in decs[:5]:
                    lines.append(f"  - [{d.decision_type.value}] {d.description[:60]}")
                for m in mems[:5]:
                    lines.append(f"  - {m.get('key', '?')}: {str(m.get('value', ''))[:60]}")
                view.update("\n".join(lines))
            self.query_one("#memory-input", Input).display = False
        finally:
            mem.close()


class WorkspaceScreen(NavScreen):
    """Multi-repo workspace status — registered repos and node counts."""

    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Static("[b]Multi-repo workspace — registered repos[/b]", id="workspace-hint")
        yield OptionList(id="workspace-actions")
        yield Input(id="workspace-input", placeholder="alias:path or query\u2026")
        yield Static("", id="workspace-view")
        yield Footer()

    def on_mount(self) -> None:
        try:
            self.query_one("#workspace-input", Input).display = False
        except Exception:
            pass
        wacts = self.query_one("#workspace-actions", OptionList)
        if wacts.option_count == 0:
            wacts.add_options([
                Option("Init workspace", id="ws-init"),
                Option("Add repo (alias:path)", id="ws-add"),
                Option("Remove repo (alias)", id="ws-remove"),
                Option("Index all repos", id="ws-index"),
                Option("Search repos", id="ws-search"),
                Option("Refresh status", id="ws-status"),
                Option("Cross-repo dependencies", id="ws-deps"),
            ])
        view = self.query_one("#workspace-view", Static)
        ws = MultiRepoWorkspace(self.app.workspace)
        try:
            status = ws.get_status()
        finally:
            ws.close()
        if not status.get("repos"):
            view.update("[yellow]No repos registered in workspace.json.[/yellow]")
            return
        lines = [f"[b]{status['name']}[/b] — {status['repos']} repo(s)"]
        for repo in status.get("repo_status", []):
            lines.append(
                f"  • {repo['alias']}  {_shorten(repo['path'])}  "
                f"[dim]{repo['nodes']} nodes[/dim]"
            )
        view.update("\n".join(lines))


    @on(OptionList.OptionSelected, "#workspace-actions")
    def _ws_action(self, event: OptionList.OptionSelected) -> None:
        view = self.query_one("#workspace-view", Static)
        ws = MultiRepoWorkspace(self.app.workspace)
        try:
            if event.option_id == "ws-init":
                if ws.config is None:
                    ws.config = WorkspaceConfig(name=self.app.workspace.name)
                    ok = ws.save_config()
                    view.update("Workspace initialized" if ok else "Init failed")
                else:
                    view.update("already initialized")
            elif event.option_id == "ws-index":
                if ws.config is None:
                    view.update("No workspace")
                else:
                    res = ws.index_all()
                    view.update("\n".join("  - " + k + ": " + str(v) + " files" for k, v in res.items()) or "No repos")
            elif event.option_id == "ws-deps":
                deps = ws.get_cross_repo_dependencies() if ws.config else {}
                if not deps:
                    view.update("No cross-repo dependencies")
                else:
                    view.update("\n".join("  - " + k + ": " + str(len(v)) + " dep(s)" for k, v in deps.items()))
            elif event.option_id == "ws-add":
                inp = self.query_one("#workspace-input", Input)
                inp.display = True
                inp.focus()
                view.update("Type alias:path then Enter (e.g. api:../api)")
                self._ws_pending = "add"
            elif event.option_id == "ws-remove":
                inp = self.query_one("#workspace-input", Input)
                inp.display = True
                inp.focus()
                view.update("Type alias then Enter")
                self._ws_pending = "remove"
            elif event.option_id == "ws-search":
                inp = self.query_one("#workspace-input", Input)
                inp.display = True
                inp.focus()
                view.update("Type search query then Enter")
                self._ws_pending = "search"
            elif event.option_id == "ws-status":
                self.on_mount_refresh_status(view)
        finally:
            ws.close()


    def on_mount_refresh_status(self, view=None) -> None:
        view = view or self.query_one("#workspace-view", Static)
        ws = MultiRepoWorkspace(self.app.workspace)
        try:
            status = ws.get_status()
        finally:
            ws.close()
        if not status.get("repos"):
            view.update("[yellow]No repos registered in workspace.json.[/yellow]")
            return
        lines = [f"[b]{status['name']}[/b] \u2014 {status['repos']} repo(s)"]
        for repo in status.get("repo_status", []):
            lines.append(f"  \u2022 {repo['alias']}  {_shorten(repo['path'])}  [dim]{repo['nodes']} nodes[/dim]")
        view.update("\n".join(lines))

    @on(Input.Submitted, "#workspace-input")
    def _ws_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        view = self.query_one("#workspace-view", Static)
        ws = MultiRepoWorkspace(self.app.workspace)
        try:
            pending = getattr(self, "_ws_pending", "")
            if pending == "add":
                if ":" in raw:
                    alias, path = raw.split(":", 1)
                    ok = ws.add_repo(alias.strip(), Path(path.strip()))
                    view.update("Repo added: " + alias.strip() if ok else "Add failed")
                else:
                    view.update("Use alias:path format")
            elif pending == "remove":
                ok = ws.remove_repo(raw)
                view.update("Repo removed: " + raw if ok else "Remove failed")
            elif pending == "search":
                if ws.config is None:
                    view.update("No workspace")
                else:
                    res = ws.search(raw, limit=10)
                    if not res:
                        view.update("No results for: " + raw)
                    else:
                        view.update("\n".join(f"  - [{r['repo']}] {r['node'].name}" for r in res[:10]))
            self.query_one("#workspace-input", Input).display = False
            self._ws_pending = ""
        finally:
            ws.close()


class LlmScreen(NavScreen):
    """Local LLM availability and model status."""

    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Static("[b]Local LLM status[/b]", id="llm-hint")
        yield OptionList(id="llm-actions")
        yield Static("", id="llm-view")
        yield Footer()

    def on_mount(self) -> None:
        lacts = self.query_one("#llm-actions", OptionList)
        if lacts.option_count == 0:
            lacts.add_options([
                Option("Download small model", id="llm-download-small"),
                Option("Download medium model", id="llm-download-medium"),
                Option("Download large model", id="llm-download-large"),
                Option("Model load status", id="llm-serve"),
                Option("Analyze intent", id="llm-analyze"),
                Option("Refresh status", id="llm-status"),
            ])
        view = self.query_one("#llm-view", Static)
        llm = get_llm()
        info = llm.get_model_info()
        lines = [
            f"llama-cpp-python installed: {'yes' if llm.is_available() else 'no'}"
        ]
        if info.get("status") == "loaded":
            lines.append(f"model: {info['model_path']}")
            lines.append(f"context size: {info['context_size']}")
            lines.append(f"gpu layers: {info['gpu_layers']}")
        else:
            lines.append(
                "model: not loaded — use `codenexus llm` CLI to load a GGUF model"
            )
        view.update("\n".join(lines))


    @on(OptionList.OptionSelected, "#llm-actions")
    def _llm_action(self, event: OptionList.OptionSelected) -> None:
        view = self.query_one("#llm-view", Static)
        llm = get_llm()
        if event.option_id == "llm-download-small":
            info = llm.RECOMMENDED_MODELS.get("small", {})
            view.update(f"Small model: {info.get('repo_id', '-')} ({info.get('size_gb', '?')} GB)")
        elif event.option_id == "llm-download-medium":
            info = llm.RECOMMENDED_MODELS.get("medium", {})
            view.update(f"Medium model: {info.get('repo_id', '-')} ({info.get('size_gb', '?')} GB)")
        elif event.option_id == "llm-download-large":
            info = llm.RECOMMENDED_MODELS.get("large", {})
            view.update(f"Large model: {info.get('repo_id', '-')} ({info.get('size_gb', '?')} GB)")
        elif event.option_id == "llm-serve":
            info = llm.get_model_info()
            view.update(f"status={info.get('status')} loaded={llm._loaded}")
        elif event.option_id == "llm-status":
            info = llm.get_model_info()
            view.update(f"available={llm.is_available()} status={info.get('status')}")
        elif event.option_id == "llm-analyze":
            view.update("Intent: " + llm.analyze_intent("fix"))


class IndexListScreen(NavScreen):
    BINDINGS = [("escape", "back", "Back")]
    def compose(self) -> ComposeResult:
        yield Static("Generated indexes", id="indexlist-hint")
        yield Static("", id="indexlist-view")
        yield Footer()

    def on_mount(self) -> None:
        view = self.query_one("#indexlist-view", Static)
        base = self.app.workspace / ".codenexus"
        lines: list[str] = []
        single = base / "index.db"
        if single.exists():
            graph = DependencyGraph(single)
            try:
                nodes = graph.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
                edges = graph.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
                files = graph.conn.execute(
                    "SELECT COUNT(DISTINCT file_path) FROM nodes"
                ).fetchone()[0]
                try:
                    updated = graph.conn.execute(
                        "SELECT MAX(updated_at) FROM nodes"
                    ).fetchone()[0]
                except Exception:
                    updated = None
            finally:
                graph.close()
            size_kb = single.stat().st_size / 1024.0
            mtime = datetime.fromtimestamp(
                single.stat().st_mtime
            ).strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"[b]Single project index[/b]\n"
                f"  Path   : {single.resolve()}\n"
                f"  Name   : {single.name}\n"
                f"  Stats  : nodes={nodes} edges={edges} files={files}\n"
                f"  Size   : {size_kb:.1f} KB\n"
                f"  Updated: {updated or mtime} (db mtime {mtime})"
            )
        repos_dir = base / "repos"
        if repos_dir.is_dir():
            for db in sorted(repos_dir.glob("*.db")):
                graph = DependencyGraph(db)
                try:
                    nodes = graph.conn.execute(
                        "SELECT COUNT(*) FROM nodes"
                    ).fetchone()[0]
                    files = graph.conn.execute(
                        "SELECT COUNT(DISTINCT file_path) FROM nodes"
                    ).fetchone()[0]
                except Exception:
                    nodes = files = 0
                finally:
                    graph.close()
                size_kb = db.stat().st_size / 1024.0
                mtime = datetime.fromtimestamp(
                    db.stat().st_mtime
                ).strftime("%Y-%m-%d %H:%M")
                lines.append(
                    f"[b]{db.stem}[/b] (repos/{db.name})\n"
                    f"  Path   : {db.resolve()}\n"
                    f"  Stats  : nodes={nodes} files={files}\n"
                    f"  Size   : {size_kb:.1f} KB\n"
                    f"  Updated: {mtime}"
                )
        if not lines:
            view.update("No index found")
            return
        lines.append(
            "Tip: paths are absolute so you can reindex from the CLI with\n"
            "  codenexus -w <path> index"
        )
        view.update("\n".join(lines))


class StatusScreen(NavScreen):
    BINDINGS = [("escape", "back", "Back")]
    def compose(self) -> ComposeResult:
        yield Static("Index status", id="status-hint")
        yield Static("", id="status-view")
        yield Footer()
    def on_mount(self) -> None:
        view = self.query_one("#status-view", Static)
        try:
            stats = self.app.workspace_stats()
        except FileNotFoundError:
            view.update("No index found")
            return
        view.update("Nodes " + str(stats["nodes"]) + " Edges " + str(stats["edges"]) + " Files " + str(stats["files"]))


class TopScreen(NavScreen):
    BINDINGS = [("escape", "back", "Back")]
    def compose(self) -> ComposeResult:
        yield Static("Top symbols", id="top-hint")
        yield Static("", id="top-view")
        yield Footer()
    def on_mount(self) -> None:
        view = self.query_one("#top-view", Static)
        db = self.app.workspace / ".codenexus" / "index.db"
        if not db.exists():
            view.update("No index found")
            return
        graph = DependencyGraph(db)
        try:
            nodes = graph.get_top_central_nodes(10)
        finally:
            graph.close()
        if not nodes:
            view.update("No nodes found")
            return
        view.update("\n".join("  - " + n.name + " (" + n.node_type + ")" for n in nodes))


class ServeScreen(NavScreen):
    BINDINGS = [("escape", "back", "Back")]
    def compose(self) -> ComposeResult:
        yield Static("MCP server", id="serve-hint")
        yield Static("", id="serve-view")
        yield Footer()
    def on_mount(self) -> None:
        view = self.query_one("#serve-view", Static)
        view.update("codenexus serve -- MCP stdio server Command: codenexus serve")


class LicenseScreen(NavScreen):
    BINDINGS = [("escape", "back", "Back")]
    def compose(self) -> ComposeResult:
        yield Static("License", id="license-hint")
        yield Static("", id="license-view")
        yield Footer()
    def on_mount(self) -> None:
        view = self.query_one("#license-view", Static)
        view.update("CodeNexus is fully open source (MIT) - all features are enabled.")


class SettingsScreen(NavScreen):
    """All engine/UI config keys editable by keyboard; persisted on Esc.

    Enter/space toggles booleans; Enter cycles numeric settings through
    presets. Esc saves to ui_config.json and returns to the dashboard.
    """

    BINDINGS = [
        ("escape", "back", "Back (save)"),
        ("space", "toggle", "Toggle"),
    ]

    def action_back(self) -> None:
        _save_ui_config(self.app.workspace, self.app.ui_config)
        super().action_back()

    def compose(self) -> ComposeResult:
        yield Static(
            "[b]Settings — Enter/space toggle · Esc = save & return[/b]",
            id="settings-hint",
        )
        yield OptionList(id="settings-list")
        yield Footer()

    def on_mount(self) -> None:
        options = self.query_one("#settings-list", OptionList)
        config = self.app.ui_config
        options.add_options(
            [Option(_setting_prompt(k, config[k]), id=k) for k in _SETTING_KEYS]
        )
        options.focus()

    @on(OptionList.OptionSelected, "#settings-list")
    def _selected(self, event: OptionList.OptionSelected) -> None:
        self._apply(event.option_id)

    def action_toggle(self) -> None:
        options = self.query_one("#settings-list", OptionList)
        if options.highlighted is None:
            return  # nothing highlighted yet — no-op instead of TypeError
        option = options.get_option_at_index(options.highlighted)
        self._apply(option.id)

    def _apply(self, key: str) -> None:
        if key not in _SETTING_KEYS:
            return
        config = self.app.ui_config
        if key in _BOOLEAN_KEYS:
            config[key] = not bool(config[key])
        else:
            presets = _CYCLE_PRESETS[key]
            current = int(config[key])
            try:
                nxt = presets[(presets.index(current) + 1) % len(presets)]
            except ValueError:
                nxt = presets[0]
            config[key] = nxt
        options = self.query_one("#settings-list", OptionList)
        idx = options.get_option_index(key)
        if idx is not None:
            options.replace_option_prompt_at_index(idx, _setting_prompt(key, config[key]))


_HELP_GLOBAL = (
    "[b]Global keys[/b]\n"
    "  Enter — activate the highlighted item\n"
    "  ↑/↓   — move the selection cursor\n"
    "  Esc   — go back one screen\n"
    "  ? / F1 — open this help\n"
    "  space — toggle values on the Settings screen\n"
)

_HELP_CONTEXT = {
    "DashboardScreen": (
        "[b]Dashboard[/b]\n"
        "  Landing screen. The right-hand menu lists every action:\n"
        "  re-index, search, pipeline, settings, index management, wizard,\n"
        "  memory, workspace, LLM, status, top symbols, MCP serve, license.\n"
        "  Highlight an entry with ↑/↓ and press Enter. Index stats appear\n"
        "  on the left (pick 'Re-index workspace' the first time).\n"
    ),
    "SearchScreen": (
        "[b]Search / Browse symbols[/b]\n"
        "  Every indexed symbol in a table (name, type, file, centrality).\n"
        "  Highlight a row with ↑/↓ and press Enter to open impact analysis\n"
        "  for that symbol. Esc returns to the dashboard.\n"
    ),
    "ImpactScreen": (
        "[b]Impact analysis[/b]\n"
        "  Shows direct and indirect dependents of the selected symbol\n"
        "  (depth configurable in Settings → Impact analysis depth).\n"
        "  Esc returns to the symbol list.\n"
    ),
    "PipelineScreen": (
        "[b]Context pipeline[/b]\n"
        "  Pick a pivot symbol (↑/↓ + Enter) to preview the context capsule\n"
        "  an agent would receive: intent, pivot files, skeletons and the\n"
        "  token estimate derived from Settings → Pipeline token budget.\n"
    ),
    "ManageScreen": (
        "[b]Index management[/b]\n"
        "  Rebuild index — full re-index from scratch.\n"
        "  Delete index — clear all data (run re-index afterwards).\n"
        "  Esc returns to the dashboard.\n"
    ),
    "WizardScreen": (
        "[b]Agent wizard[/b]\n"
        "  Step 1: pick the AI agent (arrows + Enter).\n"
        "  Step 2: pick the setup mode.\n"
        "  Step 3: pick the project directory — highlight a candidate, or\n"
        "  press Enter on 'Browse the filesystem…' (←/→ move up/down one\n"
        "  level, ↑/↓ move the cursor, Enter picks, Esc returns), or on\n"
        "  'Enter a directory manually…' to type a path directly.\n"
        "  The final screen shows the MCP config snippet to paste.\n"
    ),
    "MemoryScreen": (
        "[b]Session memory[/b]\n"
        "  Recent sessions with decisions and summaries. Actions are in the\n"
        "  list; Esc returns to the dashboard.\n"
    ),
    "WorkspaceScreen": (
        "[b]Multi-repo workspace[/b]\n"
        "  Registered repositories and their status. Entries are in the\n"
        "  list; Esc returns to the dashboard.\n"
    ),
    "LlmScreen": (
        "[b]Local LLM[/b]\n"
        "  Availability of llama-cpp-python and the configured model.\n"
        "  Actions are in the list; Esc returns to the dashboard.\n"
    ),
    "StatusScreen": (
        "[b]Index status[/b]\n"
        "  Node/edge/file counts for the current index.\n"
        "  Esc returns to the dashboard.\n"
    ),
    "TopScreen": (
        "[b]Top symbols[/b]\n"
        "  Highest-centrality nodes — the most connected code in the\n"
        "  workspace. Esc returns to the dashboard.\n"
    ),
    "ServeScreen": (
        "[b]MCP serve[/b]\n"
        "  The command and config snippet to connect AI agents to this\n"
        "  index. Esc returns to the dashboard.\n"
    ),
    "LicenseScreen": (
        "[b]License[/b]\n"
        "  License information for CodeNexus. Esc returns to the dashboard.\n"
    ),
}

_HELP_FALLBACK = (
    "[b]Navigation[/b]\n"
    "  ↑/↓ highlight · Enter activate · Esc back · ? / F1 help\n"
)


class HelpScreen(NavScreen):
    """Context-sensitive help overlay, opened with `?` or F1.

    Shows the global key reference plus a section for the screen the user
    came from (the screen below this one on the stack).
    """

    BINDINGS = [("escape", "back", "Close help")]

    def compose(self) -> ComposeResult:
        yield Static("", id="help-view")
        yield Footer()

    def on_mount(self) -> None:
        stack = self.app.screen_stack
        prev = stack[-2] if len(stack) >= 2 else None
        context = (
            _HELP_CONTEXT.get(type(prev).__name__, _HELP_FALLBACK)
            if prev is not None
            else _HELP_FALLBACK
        )
        self.query_one("#help-view", Static).update(f"{_HELP_GLOBAL}\n{context}")


class CodeNexusTUI(App):
    BINDINGS = [
        ("question_mark", "help", "Help"),
        ("f1", "help", "Help"),
    ]

    def action_help(self) -> None:
        """Open the help overlay for the current screen.

        A fresh HelpScreen instance is pushed each time so the context
        section always reflects the screen *below* it on the stack (a
        cached SCREENS singleton would keep its first on_mount context).
        """
        if isinstance(self.screen, HelpScreen):
            return
        self.push_screen(HelpScreen())
    """Keyboard-first CodeNexus TUI application."""

    CSS = """
    #dash-body { height: 1fr; }
    #dash-left { width: 40%; padding: 1; }
    #dash-right { width: 60%; }
    #stats { padding: 1; }
    #pipeline-view { padding: 1; height: auto; max-height: 15; }
    OptionList { height: auto; max-height: 10; }
    #wizard-input { display: none; }
    #wizard-tree { display: none; }
    #drive-list { display: none; }
    """

    SCREENS = {
        "search": SearchScreen,
        "impact": ImpactScreen,
        "pipeline": PipelineScreen,
        "settings": SettingsScreen,
        "manage": ManageScreen,
        "wizard": WizardScreen,
        "memory": MemoryScreen,
        "workspace": WorkspaceScreen,
        "llm": LlmScreen,
        "status": StatusScreen,
        "indexlist": IndexListScreen,
        "top": TopScreen,
        "serve": ServeScreen,
        "license": LicenseScreen,
        "help": HelpScreen,
    }

    def __init__(self, workspace: Path):
        super().__init__()
        self.workspace = Path(workspace).resolve()
        self.ui_config = _load_ui_config(self.workspace)
        self.selected_symbol: str | None = None
        self._stats_cache: dict | None = None

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen())

    def workspace_stats(self) -> dict:
        db = self.workspace / ".codenexus" / "index.db"
        if not db.exists():
            raise FileNotFoundError(str(db))
        graph = DependencyGraph(db)
        try:
            return {
                "nodes": graph.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0],
                "edges": graph.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
                "files": graph.conn.execute(
                    "SELECT COUNT(DISTINCT file_path) FROM nodes"
                ).fetchone()[0],
            }
        finally:
            graph.close()

    @property
    def version(self) -> str:
        from ._version import __version__

        return __version__

    def action_back(self) -> None:
        if self.app.screen is not None and len(self.screen_stack) > 1:
            self.pop_screen()
