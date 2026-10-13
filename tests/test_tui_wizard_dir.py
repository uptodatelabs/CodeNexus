"""TUI wizard directory menu acceptance tests (red->green).

Acceptance criteria captured as failing tests BEFORE implementing:

- W1: after choosing agent + setup mode, the wizard shows a directory
      selection menu containing the current workspace as a candidate and a
      manual-entry option (keyboard-only, no mandatory typing).
- W2: choosing a directory re-renders the MCP config for that directory and
      persists the choice to ui_config.json under `wizard_project_path`.
- W3: manual entry validates the path — a non-existent directory shows an
      error; a valid directory is accepted and rendered in the config.
- W4: a cursor-driven filesystem browse option exists; walking the tree with
      the cursor and pressing Enter applies that directory (config + persist).
- W5: Esc from the browse tree hides the tree and returns to the directory
      menu (no screen pop).
- W6: Esc from the manual-input mode hides the input and returns to the
      directory menu (no screen pop).
- W7: the browse tree is not locked to the CodeNexus workspace — going up
      one directory level (backspace) re-roots the tree at the parent, can
      repeat until the filesystem root, and Esc still returns to the menu.
"""

import json
from pathlib import Path

import pytest
from textual.widgets import DirectoryTree, Input, OptionList, Static

from codenexus.server import CodeNexusServer


@pytest.fixture(scope="module")
def indexed_ws3(tmp_path_factory):
    ws = tmp_path_factory.mktemp("tui_wizard_ws")
    pkg = ws / "pkg"
    pkg.mkdir()
    (pkg / "core.py").write_text(
        "class Engine:\n    def start(self):\n        return True\n",
        encoding="utf-8",
    )
    server = CodeNexusServer(ws)
    server.index_workspace(incremental=False)
    return ws


async def _open_wizard_to_dir_stage(app, pilot):
    """Navigate: menu -> wizard -> agent -> mode; land on the dir stage."""
    options = app.screen.query_one("#menu", OptionList)
    ids = [options.get_option_at_index(i).id for i in range(options.option_count)]
    options.highlighted = ids.index("wizard")
    await pilot.press("enter")
    await pilot.pause()

    wiz = app.screen.query_one("#wizard-list", OptionList)
    assert wiz.option_count >= 1, "wizard must list at least one agent"
    wiz.highlighted = 0
    await pilot.press("enter")
    await pilot.pause()
    wiz.highlighted = 0
    await pilot.press("enter")
    await pilot.pause()


def _option_ids(widget: OptionList) -> list:
    return [widget.get_option_at_index(i).id for i in range(widget.option_count)]


@pytest.mark.asyncio
async def test_w1_wizard_offers_directory_menu(indexed_ws3):
    """W1 — directory menu with workspace candidate + manual entry."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws3)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_wizard_to_dir_stage(app, pilot)
        wiz = app.screen.query_one("#wizard-list", OptionList)
        dir_ids = _option_ids(wiz)
        assert str(app.workspace) in dir_ids, f"workspace candidate missing: {dir_ids}"
        assert "__manual__" in dir_ids, f"manual entry option missing: {dir_ids}"


@pytest.mark.asyncio
async def test_w2_directory_choice_updates_config_and_persists(indexed_ws3):
    """W2 — config re-rendered for chosen dir; choice saved to ui_config.json."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws3)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_wizard_to_dir_stage(app, pilot)
        ws_str = str(app.workspace)
        wiz = app.screen.query_one("#wizard-list", OptionList)
        dir_ids = _option_ids(wiz)
        wiz.highlighted = dir_ids.index(ws_str)
        await pilot.press("enter")
        await pilot.pause()

        view = str(app.screen.query_one("#wizard-view", Static).render())
        assert "serve" in view, f"serve command not shown after dir choice: {view}"
        assert ws_str in view, f"chosen directory not in rendered config: {view}"

        cfg_path = indexed_ws3 / ".codenexus" / "ui_config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert cfg.get("wizard_project_path") == ws_str, (
            f"wizard_project_path not persisted: {cfg}"
        )


@pytest.mark.asyncio
async def test_w3_manual_entry_validates_path(indexed_ws3):
    """W3 — manual input: invalid path errors; valid path is applied."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws3)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_wizard_to_dir_stage(app, pilot)
        wiz = app.screen.query_one("#wizard-list", OptionList)
        dir_ids = _option_ids(wiz)
        wiz.highlighted = dir_ids.index("__manual__")
        await pilot.press("enter")
        await pilot.pause()

        inp = app.screen.query_one("#wizard-input", Input)
        # Invalid: non-existent directory -> error message, no crash.
        inp.value = str(indexed_ws3 / "does-not-exist")
        await pilot.press("enter")
        await pilot.pause()
        view = str(app.screen.query_one("#wizard-view", Static).render())
        assert "not found" in view.lower(), f"expected validation error: {view}"

        # Valid: pkg subdirectory -> applied and rendered.
        inp.value = str(indexed_ws3 / "pkg")
        await pilot.press("enter")
        await pilot.pause()
        view2 = str(app.screen.query_one("#wizard-view", Static).render())
        assert str(indexed_ws3 / "pkg") in view2, f"valid dir not applied: {view2}"
        assert "serve" in view2, f"serve command not shown after manual entry: {view2}"


@pytest.mark.asyncio
async def test_w4_browse_navigation_selects_directory(indexed_ws3):
    """W4 — cursor browsing: walking the tree and Enter applies the directory."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws3)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_wizard_to_dir_stage(app, pilot)
        wiz = app.screen.query_one("#wizard-list", OptionList)
        dir_ids = _option_ids(wiz)
        assert "__browse__" in dir_ids, f"browse option missing: {dir_ids}"
        wiz.highlighted = dir_ids.index("__browse__")
        await pilot.press("enter")
        await pilot.pause()

        tree = app.screen.query_one("#wizard-tree", DirectoryTree)
        assert tree.display, "directory tree not shown after choosing browse"
        assert str(tree.path) == str(indexed_ws3), f"tree rooted elsewhere: {tree.path}"

        # Lazy load: wait until root children exist, then walk cursor to pkg.
        target = str(indexed_ws3 / "pkg")
        moved = False
        for _ in range(40):
            node = tree.cursor_node
            if node is not None and str(getattr(node.data, "path", "")) == target:
                moved = True
                break
            await pilot.press("down")
            await pilot.pause(0.05)
        assert list(tree.root.children), "root children never loaded in tree"
        assert moved, f"cursor never reached {target}"

        await pilot.press("enter")
        await pilot.pause()

        view = str(app.screen.query_one("#wizard-view", Static).render())
        assert target in view, f"browsed directory not applied: {view}"
        cfg = json.loads(
            (indexed_ws3 / ".codenexus" / "ui_config.json").read_text(encoding="utf-8")
        )
        assert cfg.get("wizard_project_path") == target, (
            f"browsed dir not persisted: {cfg}"
        )


@pytest.mark.asyncio
async def test_w5_escape_from_browse_returns_to_dir_menu(indexed_ws3):
    """W5 — Esc in browse hides the tree and restores the directory menu."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws3)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_wizard_to_dir_stage(app, pilot)
        wiz = app.screen.query_one("#wizard-list", OptionList)
        dir_ids = _option_ids(wiz)
        wiz.highlighted = dir_ids.index("__browse__")
        await pilot.press("enter")
        await pilot.pause()
        tree = app.screen.query_one("#wizard-tree", DirectoryTree)
        assert tree.display

        await pilot.press("escape")
        await pilot.pause()

        assert not tree.display, "tree should hide after Esc"
        assert wiz.display, "directory menu should return after Esc"
        ids = _option_ids(wiz)
        assert str(app.workspace) in ids, f"candidates missing after Esc: {ids}"
        assert "__browse__" in ids and "__manual__" in ids


@pytest.mark.asyncio
async def test_w7_browse_can_navigate_above_workspace(indexed_ws3):
    """W7 — browse tree can move up beyond the CodeNexus workspace root."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws3)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_wizard_to_dir_stage(app, pilot)
        wiz = app.screen.query_one("#wizard-list", OptionList)
        dir_ids = _option_ids(wiz)
        wiz.highlighted = dir_ids.index("__browse__")
        await pilot.press("enter")
        await pilot.pause()
        tree = app.screen.query_one("#wizard-tree", DirectoryTree)
        assert tree.display

        # One level up: tree re-roots at the workspace's parent directory.
        await pilot.press("backspace")
        await pilot.pause()
        assert str(tree.path) == str(indexed_ws3.parent), (
            f"tree did not move up: {tree.path}"
        )

        # Repeated up-navigation stops at the filesystem root (no crash).
        # Depth to the drive root is environment-dependent, so press until
        # the root is observed (bounded) instead of a fixed count.
        for _ in range(12):
            await pilot.press("backspace")
            await pilot.pause()
            path = Path(str(tree.path))
            if path.parent == path:
                break
        path = Path(str(tree.path))
        assert path.parent == path, f"tree never anchored at fs root: {tree.path}"

        # Esc still returns to the directory menu.
        await pilot.press("escape")
        await pilot.pause()
        assert not tree.display, "tree should hide after Esc"
        ids = _option_ids(wiz)
        assert "__browse__" in ids and "__manual__" in ids


@pytest.mark.asyncio
async def test_w8_left_arrow_moves_up_one_directory(indexed_ws3):
    """W8 — pressing Left inside the browse tree re-roots at the parent dir.

    Users expect Left = up one level (mirroring backspace). This captures
    the defect where Backspace worked but Left did nothing.
    """
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws3)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_wizard_to_dir_stage(app, pilot)
        wiz = app.screen.query_one("#wizard-list", OptionList)
        dir_ids = _option_ids(wiz)
        wiz.highlighted = dir_ids.index("__browse__")
        await pilot.press("enter")
        await pilot.pause()
        tree = app.screen.query_one("#wizard-tree", DirectoryTree)
        assert tree.display

        # Left arrow: tree re-roots at the workspace's parent directory.
        await pilot.press("left")
        await pilot.pause()
        assert str(tree.path) == str(indexed_ws3.parent), (
            f"tree did not move up on Left: {tree.path}"
        )

        # Left again until the filesystem root — must stop, not crash.
        for _ in range(12):
            await pilot.press("left")
            await pilot.pause()
            path = Path(str(tree.path))
            if path.parent == path:
                break
        path = Path(str(tree.path))
        assert path.parent == path, f"tree never anchored at fs root via Left: {tree.path}"


@pytest.mark.asyncio
async def test_w6_escape_from_manual_returns_to_dir_menu(indexed_ws3):
    """W6 — Esc in manual mode hides the input and restores the menu."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws3)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_wizard_to_dir_stage(app, pilot)
        wiz = app.screen.query_one("#wizard-list", OptionList)
        dir_ids = _option_ids(wiz)
        wiz.highlighted = dir_ids.index("__manual__")
        await pilot.press("enter")
        await pilot.pause()
        inp = app.screen.query_one("#wizard-input", Input)
        assert inp.display

        await pilot.press("escape")
        await pilot.pause()

        assert not inp.display, "input should hide after Esc"
        ids = _option_ids(wiz)
        assert "__manual__" in ids and "__browse__" in ids, (
            f"directory menu not restored after Esc: {ids}"
        )


@pytest.mark.asyncio
async def test_w9_right_arrow_descends_one_level(indexed_ws3):
    """W9 — Right inside browse re-roots the tree one level down.

    Users expect Right = descend into the highlighted directory. Captures
    the defect where Right did nothing.
    """
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws3)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_wizard_to_dir_stage(app, pilot)
        wiz = app.screen.query_one("#wizard-list", OptionList)
        dir_ids = _option_ids(wiz)
        wiz.highlighted = dir_ids.index("__browse__")
        await pilot.press("enter")
        await pilot.pause()
        tree = app.screen.query_one("#wizard-tree", DirectoryTree)
        assert tree.display

        # Lazy load: walk cursor down to the pkg subdirectory.
        target = str(indexed_ws3 / "pkg")
        moved = False
        for _ in range(40):
            node = tree.cursor_node
            if node is not None and str(getattr(node.data, "path", "")) == target:
                moved = True
                break
            await pilot.press("down")
            await pilot.pause(0.05)
        assert moved, f"cursor never reached {target}"

        await pilot.press("right")
        await pilot.pause()
        assert str(tree.path) == target, f"Right did not descend into {target}: {tree.path}"
        assert tree.cursor_line == 0, f"stale cursor after descend: {tree.cursor_line}"
        assert tree.display, "tree should stay visible after descending"


@pytest.mark.asyncio
async def test_w10_up_at_drive_root_offers_drive_selection(indexed_ws3):
    """W10 — at a drive root, going up again opens a drive selection list.

    Choosing a drive re-roots the browse tree at that drive (no crash,
    tree stays visible).
    """
    from codenexus.tui import CodeNexusTUI, _list_drives

    drives = _list_drives()
    if len(drives) < 2:
        pytest.skip(f"only one drive present, nothing to select between: {drives}")

    app = CodeNexusTUI(indexed_ws3)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_wizard_to_dir_stage(app, pilot)
        wiz = app.screen.query_one("#wizard-list", OptionList)
        dir_ids = _option_ids(wiz)
        wiz.highlighted = dir_ids.index("__browse__")
        await pilot.press("enter")
        await pilot.pause()
        tree = app.screen.query_one("#wizard-tree", DirectoryTree)

        # Walk up to the drive root (bounded).
        for _ in range(15):
            path = Path(str(tree.path))
            if path.parent == path:
                break
            await pilot.press("backspace")
            await pilot.pause()
        assert Path(str(tree.path)).parent == Path(str(tree.path)), (
            f"tree never reached drive root: {tree.path}"
        )

        # One more up at a drive root -> the drive selection list appears.
        await pilot.press("backspace")
        await pilot.pause()
        drive_list = app.screen.query_one("#drive-list", OptionList)
        assert drive_list.display, "drive selection list not shown at drive root"
        ids = [
            drive_list.get_option_at_index(i).id
            for i in range(drive_list.option_count)
        ]
        assert ids, "drive selection list is empty"

        current_anchor = str(Path(str(indexed_ws3)).anchor)
        others = [d for d in ids if str(d).upper() != current_anchor.strip("\\").upper() + ":"]
        chosen = str(others[0]) if others else str(ids[0])
        drive_list.highlighted = ids.index(chosen)
        await pilot.press("enter")
        await pilot.pause()

        assert not drive_list.display, "drive list should hide after choosing"
        assert tree.display, "tree should be visible after choosing a drive"
        assert str(tree.path).upper().startswith(chosen[0]), (
            f"tree not re-rooted at chosen drive {chosen}: {tree.path}"
        )


@pytest.mark.asyncio
async def test_w11_reentering_browse_resets_tree_view(indexed_ws3):
    """W11 — re-entering the browse stage renders a fresh full-height tree.

    Captures the defect where entering browse, leaving (Esc), and entering
    again showed a half-rendered/stale tree (stale cursor beyond content).
    """
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws3)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_wizard_to_dir_stage(app, pilot)
        wiz = app.screen.query_one("#wizard-list", OptionList)
        dir_ids = _option_ids(wiz)
        wiz.highlighted = dir_ids.index("__browse__")
        await pilot.press("enter")
        await pilot.pause()
        tree = app.screen.query_one("#wizard-tree", DirectoryTree)
        assert tree.display

        # Move the cursor away from the top, then leave and re-enter.
        await pilot.press("down")
        await pilot.pause(0.05)
        await pilot.press("escape")
        await pilot.pause()
        assert not tree.display

        ids = _option_ids(wiz)
        wiz.highlighted = ids.index("__browse__")
        await pilot.press("enter")
        await pilot.pause()
        tree = app.screen.query_one("#wizard-tree", DirectoryTree)
        assert tree.display, "tree not visible on re-entry"
        assert str(tree.path) == str(indexed_ws3), f"stale path on re-entry: {tree.path}"
        assert tree.cursor_line == 0, (
            f"stale cursor position on re-entry (half-render viewport): {tree.cursor_line}"
        )
