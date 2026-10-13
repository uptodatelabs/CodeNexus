"""S1-S4: TUI full settings coverage — every config key editable by keyboard.

Red-first acceptance criteria (captured before implementing the expanded
SettingsScreen; red->green protocol):

- S1: Settings screen lists every engine/UI config key:
      memory_enabled, llm_enabled, max_tokens, search_limit, impact_depth.
- S2: A numeric setting cycles through preset values with Enter; the change
      persists to ui_config.json and survives an app restart.
- S3: Boolean settings toggle with Enter and space; the change persists.
- S4: The impact screen honours the persisted impact_depth.
"""

from __future__ import annotations

import json

import pytest
from textual.widgets import OptionList, Static

from codenexus.server import CodeNexusServer

SETTING_KEYS = (
    "memory_enabled",
    "llm_enabled",
    "max_tokens",
    "search_limit",
    "impact_depth",
)


def _cfg_path(ws):
    return ws / ".codenexus" / "ui_config.json"


def _read_cfg(ws):
    p = _cfg_path(ws)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


async def _open_settings(pilot):
    menu = pilot.app.screen.query_one(OptionList)
    menu.highlighted = 3  # Settings entry on the dashboard menu
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()


@pytest.fixture(scope="module")
def chain_ws(tmp_path_factory):
    """Indexed workspace with an Alpha<-Beta<-Gamma chain for depth checks."""
    ws = tmp_path_factory.mktemp("settings_ws")
    pkg = ws / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("class Alpha:\n    def run(self):\n        return 1\n", encoding="utf-8")
    (pkg / "b.py").write_text("from pkg.a import Alpha\n\n\nclass Beta(Alpha):\n    pass\n", encoding="utf-8")
    (pkg / "c.py").write_text("from pkg.b import Beta\n\n\nclass Gamma(Beta):\n    pass\n", encoding="utf-8")
    server = CodeNexusServer(ws)
    server.index_workspace(incremental=False)
    return ws


@pytest.fixture()
def fresh_config(chain_ws):
    _cfg_path(chain_ws).unlink(missing_ok=True)
    return chain_ws


@pytest.mark.asyncio
async def test_s1_settings_lists_all_config_keys(fresh_config):
    """S1 — settings screen exposes every engine/UI config key."""
    from codenexus.tui import CodeNexusTUI, SettingsScreen

    app = CodeNexusTUI(fresh_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_settings(pilot)
        assert isinstance(app.screen, SettingsScreen)
        options = app.screen.query_one("#settings-list", OptionList)
        ids = {options.get_option_at_index(i).id for i in range(options.option_count)}
        assert ids == set(SETTING_KEYS)


@pytest.mark.asyncio
async def test_s2_max_tokens_cycle_persists_across_restart(fresh_config):
    """S2 — Enter cycles a numeric setting; value survives an app restart."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(fresh_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_settings(pilot)
        options = app.screen.query_one("#settings-list", OptionList)
        idx = SETTING_KEYS.index("max_tokens")
        options.highlighted = idx
        await pilot.pause()
        await pilot.press("enter")  # 8000 -> 16000
        await pilot.pause()
        assert options.get_option_at_index(idx).prompt == "Pipeline token budget: 16000"
        await pilot.press("escape")  # save + back
        await pilot.pause()
    assert _read_cfg(fresh_config)["max_tokens"] == 16000

    # Restart the app: the persisted value must be shown again.
    app2 = CodeNexusTUI(fresh_config)
    async with app2.run_test() as pilot:
        await pilot.pause()
        await _open_settings(pilot)
        options2 = app2.screen.query_one("#settings-list", OptionList)
        assert (
            options2.get_option_at_index(SETTING_KEYS.index("max_tokens")).prompt
            == "Pipeline token budget: 16000"
        )


@pytest.mark.asyncio
async def test_s3_boolean_toggles_by_enter_and_space(fresh_config):
    """S3 — Enter and space toggle boolean settings; both persist."""
    from codenexus.tui import CodeNexusTUI

    app = CodeNexusTUI(fresh_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_settings(pilot)
        options = app.screen.query_one("#settings-list", OptionList)
        # memory_enabled (index 0): True -> False via Enter
        options.highlighted = SETTING_KEYS.index("memory_enabled")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        # llm_enabled (index 1): False -> True via space
        options.highlighted = SETTING_KEYS.index("llm_enabled")
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    data = _read_cfg(fresh_config)
    assert data["memory_enabled"] is False
    assert data["llm_enabled"] is True


@pytest.mark.asyncio
async def test_s4_impact_screen_uses_configured_depth(chain_ws):
    """S4 — impact view honours the persisted impact_depth setting."""
    from codenexus.graph import DependencyGraph
    from codenexus.tui import CodeNexusTUI

    # depth=1: only direct dependents -> no "depth N" lines rendered.
    cfg = _cfg_path(chain_ws)
    base = _read_cfg(chain_ws)
    base["impact_depth"] = 1
    cfg.write_text(json.dumps(base), encoding="utf-8")

    graph = DependencyGraph(chain_ws / ".codenexus" / "index.db")
    try:
        alpha = graph.search_nodes("Alpha", limit=1)[0]
    finally:
        graph.close()

    app = CodeNexusTUI(chain_ws)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.selected_symbol = alpha.id
        app.push_screen("impact")
        await pilot.pause()
        view = str(app.screen.query_one("#impact-view", Static).render())
        assert "depth 2" not in view
        assert "Beta" in view

    # depth=2: Gamma appears as an indirect dependent at depth 2.
    base["impact_depth"] = 2
    cfg.write_text(json.dumps(base), encoding="utf-8")
    app2 = CodeNexusTUI(chain_ws)
    async with app2.run_test() as pilot:
        await pilot.pause()
        app2.selected_symbol = alpha.id
        app2.push_screen("impact")
        await pilot.pause()
        view = str(app2.screen.query_one("#impact-view", Static).render())
        assert "depth 2" in view
        assert "Gamma" in view
