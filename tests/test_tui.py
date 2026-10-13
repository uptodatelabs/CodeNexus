"""TUI (Textual) acceptance tests — keyboard-first UI for CodeNexus.

Acceptance criteria captured as failing tests BEFORE implementing
codenexus/tui.py (red->green protocol):

- T1: `CodeNexusTUI` launches into a dashboard screen showing index stats
      and a 5-item action menu (all reachable by keyboard).
- T2: Every destination (search, settings) is reachable with arrows + Enter
      only — no typing required.
- T3: Settings screen toggles an option by keyboard and persists it to
      <workspace>/.codenexus/ui_config.json.
- T4: Search screen lists indexed symbols in a table; picking a row by
      keyboard opens the impact view for that symbol.
- T5: Pipeline screen lets the user pick a symbol and shows a context
      capsule with a token estimate.
- T6: The "Re-index workspace" menu action rebuilds the index (observable:
      stats go back to nodes > 0 after the index was cleared).
- T7: The `codenexus ui` CLI command exists.
"""

import json

import pytest
from click.testing import CliRunner
from textual.widgets import DataTable, OptionList, Static

from codenexus.server import CodeNexusServer


@pytest.fixture(scope="module")
def indexed_ws(tmp_path_factory):
    """A workspace with two indexed python files."""
    ws = tmp_path_factory.mktemp("tui_ws")
    pkg = ws / "pkg"
    pkg.mkdir()
    (pkg / "core.py").write_text(
        "class Engine:\n    def start(self):\n        return True\n",
        encoding="utf-8",
    )
    (pkg / "app.py").write_text(
        "from pkg.core import Engine\n\n\ndef main():\n"
        "    engine = Engine()\n    engine.start()\n    return engine\n",
        encoding="utf-8",
    )
    server = CodeNexusServer(ws)
    server.index_workspace(incremental=False)
    return ws


async def _activate_menu(pilot, position):
    """Highlight dashboard menu entry `position` (0-based) and activate it."""
    options = pilot.app.screen.query_one(OptionList)
    options.highlighted = position
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()


def test_cli_ui_command_exists():
    """T7 — `codenexus ui` is a registered CLI command."""
    from codenexus.cli import main

    result = CliRunner().invoke(main, ["ui", "--help"])
    assert result.exit_code == 0, result.output
    assert "ui" in result.output


@pytest.mark.asyncio
async def test_t1_dashboard_launch(indexed_ws):
    """T1 — dashboard screen with stats and a 5-item menu."""
    from codenexus.tui import CodeNexusTUI, DashboardScreen

    app = CodeNexusTUI(indexed_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
        stats = str(app.screen.query_one("#stats", Static).render())
        assert "nodes" in stats.lower()
        options = app.screen.query_one(OptionList)
        assert options.option_count == 16, options.option_count  # reindex/search/pipeline/settings/manage/wizard/memory/workspace/llm/status/indexlist/top/serve/license/help/quit


@pytest.mark.asyncio
async def test_t2_destinations_reachable_by_keyboard(indexed_ws):
    """T2 — search and settings screens via arrows + Enter only."""
    from codenexus.tui import CodeNexusTUI, SearchScreen, SettingsScreen

    app = CodeNexusTUI(indexed_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _activate_menu(pilot, 1)  # Browse & search symbols
        assert isinstance(app.screen, SearchScreen)
        await pilot.press("escape")
        await pilot.pause()
        await _activate_menu(pilot, 3)  # Settings
        assert isinstance(app.screen, SettingsScreen)


@pytest.mark.asyncio
async def test_t3_settings_toggle_persist(indexed_ws):
    """T3 — keyboard toggle in settings persisted to ui_config.json."""
    from codenexus.tui import CodeNexusTUI, SettingsScreen

    cfg = indexed_ws / ".codenexus" / "ui_config.json"
    if cfg.exists():
        cfg.unlink()

    app = CodeNexusTUI(indexed_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _activate_menu(pilot, 3)  # Settings
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        await pilot.press("space")  # toggle the first option (memory)
        await pilot.pause()
        await pilot.press("escape")  # leave settings -> save
        await pilot.pause()

    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert isinstance(data.get("memory_enabled"), bool)


@pytest.mark.asyncio
async def test_t4_search_pick_symbol_by_keyboard(indexed_ws):
    """T4 — symbol table row selection opens the impact view."""
    from codenexus.tui import CodeNexusTUI, ImpactScreen, SearchScreen

    app = CodeNexusTUI(indexed_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _activate_menu(pilot, 1)  # Browse & search symbols
        await pilot.pause()
        assert isinstance(app.screen, SearchScreen)
        table = app.screen.query_one(DataTable)
        assert table.row_count >= 1
        table.focus()
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ImpactScreen)


@pytest.mark.asyncio
async def test_t5_pipeline_capsule_for_selected_symbol(indexed_ws):
    """T5 — pipeline screen renders a capsule with a token estimate."""
    from codenexus.tui import CodeNexusTUI, PipelineScreen

    app = CodeNexusTUI(indexed_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _activate_menu(pilot, 2)  # Context pipeline
        await pilot.pause()
        assert isinstance(app.screen, PipelineScreen)
        options = app.screen.query_one(OptionList)
        assert options.option_count >= 1
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        view = str(app.screen.query_one("#pipeline-view", Static).render())
        assert "Token estimate" in view


@pytest.mark.asyncio
async def test_t6_reindex_menu_action(indexed_ws):
    """T6 — re-index from the menu rebuilds a cleared index."""
    from codenexus.tui import CodeNexusTUI

    server = CodeNexusServer(indexed_ws)
    server.clear_index()  # observable precondition: index empty

    app = CodeNexusTUI(indexed_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _activate_menu(pilot, 0)  # Re-index workspace
        await pilot.pause()
        stats = str(app.screen.query_one("#stats", Static).render()).lower()
        assert "0 nodes" not in stats
        assert "nodes" in stats
