"""TUI full-control acceptance tests (red->green).

Every CLI command group must be reachable from the TUI without typing
a raw CLI command:
  F1: dashboard offers status / top / serve / license entries
  F2: status screen renders node/edge/file counts
  F3: top screen renders central nodes
  F4: serve screen renders the MCP serve command
  F5: license screen renders the open-source status
  F6: memory screen offers start/stats/search actions (keyboard)
  F7: workspace screen offers init/index/deps actions (keyboard)
  F8: llm screen offers download options + analyze (keyboard)
"""

import pytest
from textual.widgets import OptionList, Static


@pytest.fixture(scope="module")
def full_ws(tmp_path_factory):
    ws = tmp_path_factory.mktemp("tui_full_ws")
    (ws / "app.py").write_text(
        "class Engine:\n    def run(self):\n        return 1\n", encoding="utf-8"
    )
    from codenexus.server import CodeNexusServer

    CodeNexusServer(ws).index_workspace(incremental=False)
    return ws


def _menu_ids(app):
    menu = app.screen.query_one("#menu", OptionList)
    return [menu.get_option_at_index(i).id for i in range(menu.option_count)]


async def _goto(app, pilot, option_id: str):
    menu = app.screen.query_one("#menu", OptionList)
    ids = [menu.get_option_at_index(i).id for i in range(menu.option_count)]
    menu.highlighted = ids.index(option_id)
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.asyncio
async def test_f1_dashboard_offers_all_entries(full_ws):
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(full_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        ids = _menu_ids(app)
        for want in ("status", "top", "serve", "license"):
            assert want in ids, f"{want} entry missing: {ids}"


@pytest.mark.asyncio
async def test_f2_status_screen_shows_counts(full_ws):
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(full_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _goto(app, pilot, "status")
        text = str(app.screen.query_one("#status-view", Static).render())
        assert "Nodes" in text, f"status not shown: {text}"


@pytest.mark.asyncio
async def test_f3_top_screen_lists_nodes(full_ws):
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(full_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _goto(app, pilot, "top")
        text = str(app.screen.query_one("#top-view", Static).render())
        assert "Engine" in text, f"top nodes not shown: {text}"


@pytest.mark.asyncio
async def test_f4_serve_screen_shows_command(full_ws):
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(full_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _goto(app, pilot, "serve")
        text = str(app.screen.query_one("#serve-view", Static).render())
        assert "serve" in text, f"serve command not shown: {text}"


@pytest.mark.asyncio
async def test_f5_license_screen_shows_status(full_ws):
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(full_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _goto(app, pilot, "license")
        text = str(app.screen.query_one("#license-view", Static).render())
        assert "MIT" in text, f"license not shown: {text}"


@pytest.mark.asyncio
async def test_f6_memory_screen_offers_actions(full_ws):
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(full_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _goto(app, pilot, "memory")
        actions = app.screen.query_one("#memory-actions", OptionList)
        ids = [actions.get_option_at_index(i).id for i in range(actions.option_count)]
        for want in ("mem-start", "mem-stats", "mem-search"):
            assert want in ids, f"memory action {want} missing: {ids}"


@pytest.mark.asyncio
async def test_f7_workspace_screen_offers_actions(full_ws):
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(full_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _goto(app, pilot, "workspace")
        actions = app.screen.query_one("#workspace-actions", OptionList)
        ids = [actions.get_option_at_index(i).id for i in range(actions.option_count)]
        for want in ("ws-init", "ws-index", "ws-deps"):
            assert want in ids, f"workspace action {want} missing: {ids}"


@pytest.mark.asyncio
async def test_f8_llm_screen_offers_actions(full_ws):
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(full_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _goto(app, pilot, "llm")
        actions = app.screen.query_one("#llm-actions", OptionList)
        ids = [actions.get_option_at_index(i).id for i in range(actions.option_count)]
        for want in ("llm-download-small", "llm-analyze"):
            assert want in ids, f"llm action {want} missing: {ids}"
