"""Help system acceptance tests (H1–H5) — red->green protocol.

Acceptance criteria captured as failing tests BEFORE implementing
the help system in codenexus/tui.py and codenexus/cli.py:

- H1: pressing '?' from any screen opens a help overlay; Esc closes it
      and returns to the previous screen.
- H2: the overlay shows an overview (global keys) plus context-specific
      content for the current screen.
- H3: 'F1' opens help from a deeper screen (Settings) and closing it
      returns there.
- H4: the dashboard menu has a visible "Help" entry (option count 15),
      selectable by keyboard.
- H5: `codenexus help` is a registered CLI command printing a short guide.
"""

import pytest
from click.testing import CliRunner
from textual.widgets import OptionList, Static

from tests.test_tui import indexed_ws  # noqa: F401 -- pytest fixture reuse


async def _activate_menu(pilot, position):
    """Highlight dashboard menu entry `position` (0-based) and activate it."""
    options = pilot.app.screen.query_one(OptionList)
    options.highlighted = position
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.asyncio
async def test_h1_question_mark_opens_help_and_escape_closes(indexed_ws):
    """H1 — '?' opens the help overlay; Esc returns to the dashboard."""
    from codenexus.tui import CodeNexusTUI, DashboardScreen, HelpScreen

    app = CodeNexusTUI(indexed_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)


@pytest.mark.asyncio
async def test_h2_help_is_context_aware(indexed_ws):
    """H2 — overlay shows global keys AND per-screen context text."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(indexed_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        overview = str(app.screen.query_one("#help-view", Static).render())
        assert "Enter" in overview  # global keys section
        assert "Esc" in overview
        assert "Dashboard" in overview  # current screen section

        await pilot.press("escape")
        await pilot.pause()
        await _activate_menu(pilot, 1)  # Search screen
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        search_help = str(app.screen.query_one("#help-view", Static).render())
        assert "Search" in search_help  # context switches per screen
        assert search_help != overview


@pytest.mark.asyncio
async def test_h3_f1_from_deeper_screen_returns_there(indexed_ws):
    """H3 — F1 opens help on Settings; closing returns to Settings."""
    from codenexus.tui import CodeNexusTUI, HelpScreen, SettingsScreen

    app = CodeNexusTUI(indexed_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _activate_menu(pilot, 3)  # Settings
        assert isinstance(app.screen, SettingsScreen)
        await pilot.press("f1")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)


@pytest.mark.asyncio
async def test_h4_dashboard_menu_has_help_entry(indexed_ws):
    """H4 — visible Help entry in the dashboard menu, keyboard reachable."""
    from codenexus.tui import CodeNexusTUI, HelpScreen

    app = CodeNexusTUI(indexed_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        options = app.screen.query_one(OptionList)
        assert options.option_count == 16, options.option_count
        await _activate_menu(pilot, 14)  # Help entry (before Quit; indexlist shifted it)
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)


def test_h5_cli_help_command_exists():
    """H5 — `codenexus help` prints a short usage guide."""
    from codenexus.cli import main

    result = CliRunner().invoke(main, ["help"])
    assert result.exit_code == 0, result.output
    assert "index" in result.output
    assert "search" in result.output


@pytest.mark.asyncio
async def test_h6_repeated_question_mark_does_not_stack_help(indexed_ws):
    """H6 — pressing '?' again while help is open must NOT stack another
    HelpScreen; the stack depth stays the same and Esc still closes."""
    from codenexus.tui import CodeNexusTUI, DashboardScreen, HelpScreen

    app = CodeNexusTUI(indexed_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        depth_before = len(app.screen_stack)
        await pilot.press("question_mark")
        await pilot.pause()
        assert len(app.screen_stack) == depth_before, (
            f"HelpScreen stacked: depth {depth_before} -> {len(app.screen_stack)}"
        )
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
