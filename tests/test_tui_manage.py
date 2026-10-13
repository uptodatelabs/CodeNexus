"""TUI index management + wizard acceptance tests (red->green).

Acceptance criteria captured as failing tests BEFORE implementing:

- M1: Dashboard menu offers "Index management" and "Agent wizard" entries.
- M2: Index management screen can DELETE the index (observable: node count
      drops to 0 in the stats panel after clearing).
- M3: Index management screen can REBUILD (full re-index) the index
      (observable: node count becomes > 0 again after a clear).
- M4: Wizard screen (keyboard-only, no text input) lists agents and, after
      choosing agent + mode, shows an MCP config containing the codenexus
      serve command.
"""

import pytest
from textual.widgets import OptionList, Static

from codenexus.server import CodeNexusServer


@pytest.fixture(scope="module")
def indexed_ws2(tmp_path_factory):
    ws = tmp_path_factory.mktemp("tui_manage_ws")
    pkg = ws / "pkg"
    pkg.mkdir()
    (pkg / "core.py").write_text(
        "class Engine:\n    def start(self):\n        return True\n",
        encoding="utf-8",
    )
    server = CodeNexusServer(ws)
    server.index_workspace(incremental=False)
    return ws


def _menu_ids(app) -> list:
    return [
        app.screen.query_one("#menu", OptionList).get_option_at_index(i).id
        for i in range(app.screen.query_one("#menu", OptionList).option_count)
    ]


@pytest.mark.asyncio
async def test_m1_dashboard_offers_manage_and_wizard(indexed_ws2):
    """M1 — dashboard menu includes index management and wizard entries."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws2)
    async with app.run_test() as pilot:
        await pilot.pause()
        ids = _menu_ids(app)
        assert "manage" in ids, f"manage entry missing: {ids}"
        assert "wizard" in ids, f"wizard entry missing: {ids}"


@pytest.mark.asyncio
async def test_m2_manage_screen_clears_index(indexed_ws2):
    """M2 — deleting the index from the management screen empties nodes."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws2)
    async with app.run_test() as pilot:
        await pilot.pause()
        options = app.screen.query_one("#menu", OptionList)
        options.highlighted = ids_index(_menu_ids(app), "manage")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        manage = app.screen.query_one("#manage-list", OptionList)
        # Find the clear/delete option and activate it.
        idx = next(
            i for i in range(manage.option_count)
            if manage.get_option_at_index(i).id == "clear"
        )
        manage.highlighted = idx
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        stats = str(app.screen.query_one("#manage-info", Static).render()).lower()
        assert "0 nodes" in stats, f"expected 0 nodes after clear: {stats}"


@pytest.mark.asyncio
async def test_m3_manage_screen_rebuilds_index(indexed_ws2):
    """M3 — rebuilding from the management screen restores nodes > 0."""
    from codenexus.tui import CodeNexusTUI

    # Precondition: index cleared.
    CodeNexusServer(indexed_ws2).clear_index()

    app = CodeNexusTUI(indexed_ws2)
    async with app.run_test() as pilot:
        await pilot.pause()
        options = app.screen.query_one("#menu", OptionList)
        options.highlighted = ids_index(_menu_ids(app), "manage")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        manage = app.screen.query_one("#manage-list", OptionList)
        idx = next(
            i for i in range(manage.option_count)
            if manage.get_option_at_index(i).id == "rebuild"
        )
        manage.highlighted = idx
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        stats = str(app.screen.query_one("#manage-info", Static).render()).lower()
        assert "0 nodes" not in stats, f"expected nodes > 0 after rebuild: {stats}"
        assert "nodes" in stats


def ids_index(ids, wanted):
    return ids.index(wanted)


@pytest.mark.asyncio
async def test_m4_wizard_shows_mcp_config(indexed_ws2):
    """M4 — wizard: agent -> mode choice renders MCP config without typing."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws2)
    async with app.run_test() as pilot:
        await pilot.pause()
        options = app.screen.query_one("#menu", OptionList)
        options.highlighted = ids_index(_menu_ids(app), "wizard")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        wiz = app.screen.query_one("#wizard-list", OptionList)
        assert wiz.option_count >= 1, "wizard must list at least one agent"
        # Pick the first agent.
        wiz.highlighted = 0
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        # Pick the first setup mode (single project).
        wiz.highlighted = 0
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        # The wizard now requires a directory choice before rendering the
        # MCP config — pick the first candidate (the current workspace).
        dir_ids = [wiz.get_option_at_index(i).id for i in range(wiz.option_count)]
        wiz.highlighted = dir_ids.index(str(app.workspace))
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        view = str(app.screen.query_one("#wizard-view", Static).render())
        assert "codenexus" in view, f"MCP config not shown: {view}"
        assert "serve" in view, f"serve command not shown: {view}"
