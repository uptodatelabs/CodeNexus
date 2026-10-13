"""TUI index list acceptance tests (red->green).

Acceptance criteria captured as failing tests BEFORE implementing:

- IL1: Dashboard menu offers an "Index list" entry.
- IL2: Index list screen shows the single-project index with stats
       (observable: alias + "nodes" count + index.db name).
- IL3: Index list screen shows "No index found" when no index exists.
- IL4: Multi-repo workspace: every generated repo db is listed by alias.
"""

import pytest
from textual.widgets import OptionList

from codenexus.graph import DependencyGraph
from codenexus.server import CodeNexusServer


@pytest.fixture(scope="module")
def indexed_ws(tmp_path_factory):
    ws = tmp_path_factory.mktemp("tui_indexlist_ws")
    pkg = ws / "pkg"
    pkg.mkdir()
    (pkg / "core.py").write_text(
        "class Engine:\n    def start(self):\n        return True\n",
        encoding="utf-8",
    )
    CodeNexusServer(ws).index_workspace(incremental=False)
    return ws


def _menu_ids(app):
    menu = app.screen.query_one("#menu", OptionList)
    return [menu.get_option_at_index(i).id for i in range(menu.option_count)]


async def _open_indexlist(app, pilot):
    menu = app.screen.query_one("#menu", OptionList)
    menu.highlighted = _menu_ids(app).index("indexlist")
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.asyncio
async def test_il1_dashboard_offers_index_list(indexed_ws):
    """IL1 — dashboard menu includes an index list entry."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        ids = _menu_ids(app)
        assert "indexlist" in ids, f"index list entry missing: {ids}"


@pytest.mark.asyncio
async def test_il2_index_list_shows_single_index(indexed_ws):
    """IL2 — index list shows the generated single index with stats."""
    from textual.widgets import Static

    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_indexlist(app, pilot)
        view = str(app.screen.query_one("#indexlist-view", Static).render())
        assert "nodes" in view, f"node stats not shown: {view}"
        assert "index.db" in view, f"index db not listed: {view}"


@pytest.mark.asyncio
async def test_il3_index_list_without_index(tmp_path):
    """IL3 — no generated index means a clear 'No index found' message."""
    from textual.widgets import Static

    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_indexlist(app, pilot)
        view = str(app.screen.query_one("#indexlist-view", Static).render())
        assert "No index found" in view, f"unexpected view: {view}"


@pytest.mark.asyncio
async def test_il5_index_list_refreshes_after_reindex(tmp_path):
    """IL5 — re-entering index list after a reindex shows the new index.

    Regression: SCREENS-registered screens are cached singletons, so
    on_mount ran only once and stale "No index found" stayed visible
    after the index was created.
    """
    from textual.widgets import Static

    from codenexus.tui import CodeNexusTUI

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "core.py").write_text("def run():\n    return None\n", encoding="utf-8")

    app = CodeNexusTUI(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        # First visit: no index yet.
        await _open_indexlist(app, pilot)
        view = str(app.screen.query_one("#indexlist-view", Static).render())
        assert "No index found" in view, f"expected empty state: {view}"
        # Leave the screen.
        await pilot.press("escape")
        await pilot.pause()
        # Generate the index outside the screen (same path as Reindex workspace).
        CodeNexusServer(tmp_path).index_workspace(incremental=False)
        # Re-enter: the list must reflect the new index.
        await _open_indexlist(app, pilot)
        view = str(app.screen.query_one("#indexlist-view", Static).render())
        assert "nodes" in view, f"index not shown after reindex: {view}"
        assert "index.db" in view, f"index db not listed after reindex: {view}"


@pytest.mark.asyncio
async def test_il4_index_list_lists_repo_dbs(tmp_path):
    """IL4 — every repo db in the workspace is listed by alias."""
    from textual.widgets import Static

    from codenexus.tui import CodeNexusTUI

    repos = tmp_path / ".codenexus" / "repos"
    repos.mkdir(parents=True)
    for alias in ("alpha", "beta"):
        DependencyGraph(repos / f"{alias}.db").close()

    app = CodeNexusTUI(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_indexlist(app, pilot)
        view = str(app.screen.query_one("#indexlist-view", Static).render())
        assert "alpha" in view, f"repo alpha not listed: {view}"
        assert "beta" in view, f"repo beta not listed: {view}"


@pytest.mark.asyncio
async def test_il6_index_list_shows_absolute_path_and_meta(indexed_ws):
    """IL6 — the single index entry shows its absolute path, size and modified time."""
    from textual.widgets import Static

    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_indexlist(app, pilot)
        view = str(app.screen.query_one("#indexlist-view", Static).render())
        db = (indexed_ws / ".codenexus" / "index.db").resolve()
        assert "Path" in view, f"absolute path entry missing: {view}"
        assert str(db) in view, f"absolute index path not shown: {view}"
        assert "Size" in view, f"size not shown: {view}"
        assert "Updated" in view, f"modified time not shown: {view}"
        assert "nodes=" in view, f"node stats not shown: {view}"


@pytest.mark.asyncio
async def test_il7_repo_entries_show_path_and_meta(tmp_path):
    """IL7 — repo db entries show their absolute path and stats too."""
    from textual.widgets import Static

    from codenexus.tui import CodeNexusTUI

    repos = tmp_path / ".codenexus" / "repos"
    repos.mkdir(parents=True)
    DependencyGraph(repos / "alpha.db").close()

    app = CodeNexusTUI(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_indexlist(app, pilot)
        view = str(app.screen.query_one("#indexlist-view", Static).render())
        db = (tmp_path / ".codenexus" / "repos" / "alpha.db").resolve()
        assert str(db) in view, f"repo absolute path not shown: {view}"
        assert "nodes=" in view, f"repo stats not shown: {view}"
        assert "Updated" in view, f"repo modified time not shown: {view}"
