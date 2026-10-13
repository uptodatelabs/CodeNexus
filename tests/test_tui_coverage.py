"""TUI full-coverage acceptance tests (red->green).

Acceptance criteria captured as failing tests BEFORE implementing:

- C1: Dashboard menu offers Memory / Workspace / LLM screens (keyboard only).
- C2: Memory screen lists recent sessions (observable: session name rendered).
- C3: Workspace screen lists registered repos and their status (observable:
      repo alias rendered on screen).
- C4: LLM screen shows local LLM availability / model status (observable:
      status text rendered on screen).
"""

import pytest
from textual.widgets import OptionList, Static

from codenexus.memory import SessionMemory
from codenexus.workspace import MultiRepoWorkspace


@pytest.fixture(scope="module")
def coverage_ws(tmp_path_factory):
    """Workspace with one memory session and one registered repo."""
    ws = tmp_path_factory.mktemp("tui_coverage_ws")
    mem = SessionMemory(ws / ".codenexus" / "memory.db")
    try:
        mem.create_session("alpha-session")
    finally:
        mem.close()
    sub = ws / "sub-repo"
    sub.mkdir()
    assert MultiRepoWorkspace(ws).add_repo("sub-repo", sub)
    return ws


@pytest.mark.asyncio
async def test_c1_dashboard_offers_memory_workspace_llm(coverage_ws):
    """C1 — dashboard menu includes memory / workspace / llm entries."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(coverage_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        menu = app.screen.query_one("#menu", OptionList)
        ids = [
            menu.get_option_at_index(i).id for i in range(menu.option_count)
        ]
        assert "memory" in ids, f"memory entry missing: {ids}"
        assert "workspace" in ids, f"workspace entry missing: {ids}"
        assert "llm" in ids, f"llm entry missing: {ids}"


@pytest.mark.asyncio
async def test_c2_memory_screen_lists_recent_sessions(coverage_ws):
    """C2 — memory screen renders recent session names."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(coverage_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        menu = app.screen.query_one("#menu", OptionList)
        ids = [
            menu.get_option_at_index(i).id for i in range(menu.option_count)
        ]
        menu.highlighted = ids.index("memory")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        text = str(app.screen.query_one("#memory-view", Static).render())
        assert "alpha-session" in text, f"session not listed: {text}"


@pytest.mark.asyncio
async def test_c3_workspace_screen_lists_repos(coverage_ws):
    """C3 — workspace screen renders registered repos."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(coverage_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        menu = app.screen.query_one("#menu", OptionList)
        ids = [
            menu.get_option_at_index(i).id for i in range(menu.option_count)
        ]
        menu.highlighted = ids.index("workspace")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        text = str(app.screen.query_one("#workspace-view", Static).render())
        assert "sub-repo" in text, f"repo not listed: {text}"


@pytest.mark.asyncio
async def test_c4_llm_screen_shows_status(coverage_ws):
    """C4 — llm screen renders model availability/status."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(coverage_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        menu = app.screen.query_one("#menu", OptionList)
        ids = [
            menu.get_option_at_index(i).id for i in range(menu.option_count)
        ]
        menu.highlighted = ids.index("llm")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        text = str(app.screen.query_one("#llm-view", Static).render())
        assert "llama" in text.lower(), f"llm status not shown: {text}"
