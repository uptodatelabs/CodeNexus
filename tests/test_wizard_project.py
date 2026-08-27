"""Wizard per-project (local-scope) registration: one agent, independent
indexes per project, stored in Claude Code's ``projects`` map in ~/.claude.json.

Tests are written against the intended public API before the implementation
exists (red), then driven green.
"""

import json

import pytest


def _fake_home(monkeypatch, tmp_path):
    fakehome = tmp_path / "fakehome"
    fakehome.mkdir()
    monkeypatch.setenv("HOME", str(fakehome))
    monkeypatch.setenv("USERPROFILE", str(fakehome))
    return fakehome


def _make_repo(root, name, symbol):
    repo = root / name
    repo.mkdir(parents=True)
    (repo / f"mod_{name}.py").write_text(
        f"def {symbol}():\n    return '{name}'\n", encoding="utf-8"
    )
    return repo


def _stub_home_for(monkeypatch, tmp_path, agent_type):
    """Point an agent's GLOBAL config_file at a tmp path (away from the real
    home) and stub out indexing. Returns the global config path."""
    from codenexus.wizard import AGENTS, AgentWizard

    fakehome = _fake_home(monkeypatch, tmp_path)
    monkeypatch.setattr(AgentWizard, "_auto_index", lambda self, p: None)
    gpath = fakehome / f"{agent_type.value}-global.cfg"
    monkeypatch.setattr(AGENTS[agent_type], "config_file", str(gpath))
    return gpath


# --------------------------------------------------------------------------- #
# apply_config_project: the local-scope engine (Claude Code)
# --------------------------------------------------------------------------- #
def test_apply_config_project_writes_local_scope_entry(tmp_path, monkeypatch):
    """apply_config_project writes projects[<dir>].mcpServers.codenexus with
    -w <dir> serve, i.e. an independent per-project index (local scope)."""
    fakehome = _fake_home(monkeypatch, tmp_path)
    from codenexus.wizard import AGENTS, AgentType, AgentWizard

    cfg = fakehome / ".claude.json"
    monkeypatch.setattr(AGENTS[AgentType.CLAUDE_CODE], "config_file", str(cfg))
    monkeypatch.setattr(AgentWizard, "_auto_index", lambda self, p: None)

    proj_a = _make_repo(tmp_path, "alpha", "alpha_symbol")
    wiz = AgentWizard()
    assert wiz.apply_config_project(AgentType.CLAUDE_CODE, proj_a) is True

    data = json.loads(cfg.read_text(encoding="utf-8"))
    key = str(proj_a)
    assert key in data["projects"], f"project key {key!r} not in projects map"
    entry = data["projects"][key]["mcpServers"]["codenexus"]
    assert entry["args"] == ["-w", str(proj_a), "serve"], entry


def test_apply_config_project_preserves_other_projects_and_keys(tmp_path, monkeypatch):
    """Adding project B must keep project A's entry and unrelated top-level keys."""
    fakehome = _fake_home(monkeypatch, tmp_path)
    from codenexus.wizard import AGENTS, AgentType, AgentWizard

    cfg = fakehome / ".claude.json"
    proj_a = _make_repo(tmp_path, "alpha", "alpha_symbol")
    proj_b = _make_repo(tmp_path, "beta", "beta_symbol")
    cfg.write_text(
        json.dumps(
            {
                "projects": {
                    str(proj_a): {
                        "mcpServers": {"codenexus": {"command": "codenexus", "args": ["-w", str(proj_a), "serve"]}}
                    }
                },
                "otherTopLevel": {"keep": "me"},
                "history": ["unchanged"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(AGENTS[AgentType.CLAUDE_CODE], "config_file", str(cfg))
    monkeypatch.setattr(AgentWizard, "_auto_index", lambda self, p: None)

    wiz = AgentWizard()
    assert wiz.apply_config_project(AgentType.CLAUDE_CODE, proj_b) is True

    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert str(proj_a) in data["projects"], "project A was clobbered"
    assert str(proj_b) in data["projects"], "project B not added"
    assert data["otherTopLevel"] == {"keep": "me"}, "unrelated top-level key lost"
    assert data["history"] == ["unchanged"], "session history lost"


def test_apply_config_project_warns_on_user_scope_conflict(tmp_path, monkeypatch, capsys):
    """A top-level (user-scope) codenexus would apply to every project and defeat
    per-project independence; the wizard must warn loudly when one is present."""
    fakehome = _fake_home(monkeypatch, tmp_path)
    from codenexus.wizard import AGENTS, AgentType, AgentWizard

    cfg = fakehome / ".claude.json"
    proj = _make_repo(tmp_path, "alpha", "alpha_symbol")
    cfg.write_text(
        json.dumps({"mcpServers": {"codenexus": {"command": "codenexus", "args": ["-w", "/old", "serve"]}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(AGENTS[AgentType.CLAUDE_CODE], "config_file", str(cfg))
    monkeypatch.setattr(AgentWizard, "_auto_index", lambda self, p: None)

    wiz = AgentWizard()
    assert wiz.apply_config_project(AgentType.CLAUDE_CODE, proj) is True

    out = capsys.readouterr().out
    assert "user-scope" in out.lower() or "global" in out.lower() or "shadow" in out.lower(), (
        "expected a warning about the existing user-scope codenexus entry"
    )
    # The local-scope entry is still written.
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert str(proj) in data["projects"]


def test_apply_config_project_unsupported_agent(tmp_path, monkeypatch, capsys):
    """Per-project local scope via the projects map is Claude Code-specific;
    other agents must get a clear 'not supported' message, not a broken write."""
    fakehome = _fake_home(monkeypatch, tmp_path)
    from codenexus.wizard import AGENTS, AgentType, AgentWizard

    cfg = fakehome / "cursor" / "mcp.json"
    cfg.parent.mkdir(parents=True)
    monkeypatch.setattr(AGENTS[AgentType.CURSOR], "config_file", str(cfg))
    monkeypatch.setattr(AgentWizard, "_auto_index", lambda self, p: None)

    proj = _make_repo(tmp_path, "alpha", "alpha_symbol")
    wiz = AgentWizard()
    result = wiz.apply_config_project(AgentType.CURSOR, proj)
    assert result is False, "non-Claude-Code agent must not get a fake local-scope write"
    out = capsys.readouterr().out
    assert "not supported" in out.lower() or "claude code" in out.lower(), (
        "expected a clear unsupported message for non-Claude-Code agents"
    )
    assert not cfg.exists(), "no file should be written for an unsupported agent"


# --------------------------------------------------------------------------- #
# CLI: codenexus wizard setup <agent> --scope local -p <project>
# --------------------------------------------------------------------------- #
def test_cli_setup_scope_local_writes_project_entry(tmp_path, monkeypatch):
    """`wizard setup claude --scope local -p <A>` writes a local-scope entry."""
    fakehome = _fake_home(monkeypatch, tmp_path)
    from click.testing import CliRunner

    from codenexus.cli import main
    from codenexus.wizard import AGENTS, AgentType, AgentWizard

    proj = _make_repo(tmp_path, "alpha", "alpha_symbol")
    cfg = fakehome / ".claude.json"
    monkeypatch.setattr(AGENTS[AgentType.CLAUDE_CODE], "config_file", str(cfg))
    # Avoid spawning the indexer subprocess (uses real `codenexus` on PATH).
    monkeypatch.setattr(AgentWizard, "_auto_index", lambda self, p: None)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["wizard", "setup", "claude", "--scope", "local", "--project", str(proj)],
        input="y\n",
    )
    assert result.exit_code == 0, result.output
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert str(proj) in data["projects"]
    assert data["projects"][str(proj)]["mcpServers"]["codenexus"]["args"] == ["-w", str(proj), "serve"]


def test_cli_setup_default_scope_still_writes_user_scope(tmp_path, monkeypatch):
    """Without --scope local, setup keeps the existing global (user-scope) behavior
    (top-level mcpServers), so the new flag is additive and non-breaking."""
    fakehome = _fake_home(monkeypatch, tmp_path)
    from click.testing import CliRunner

    from codenexus.cli import main
    from codenexus.wizard import AGENTS, AgentType, AgentWizard

    proj = _make_repo(tmp_path, "alpha", "alpha_symbol")
    cfg = fakehome / ".claude.json"
    monkeypatch.setattr(AGENTS[AgentType.CLAUDE_CODE], "config_file", str(cfg))
    monkeypatch.setattr(AgentWizard, "_auto_index", lambda self, p: None)

    runner = CliRunner()
    result = runner.invoke(
        main, ["wizard", "setup", "claude", "--project", str(proj)], input="y\n"
    )
    assert result.exit_code == 0, result.output
    data = json.loads(cfg.read_text(encoding="utf-8"))
    # No projects map; global top-level mcpServers (existing behavior).
    assert "mcpServers" in data
    assert "codenexus" in data["mcpServers"]
    assert data.get("projects") in (None, {})


# --------------------------------------------------------------------------- #
# Project-local config file agents (Cursor, Copilot, Zed, Codex, OpenCode,
# Antigravity, Continue). Each writes a project-local MCP config file so the
# index loads only inside that project — independent per-project indexes.
# --------------------------------------------------------------------------- #
PROJECT_FILE_AGENTS = [
    # (agent_type, relpath_inside_project, top_level_key)
    ("cursor", ".cursor/mcp.json", "mcpServers"),
    ("copilot", ".vscode/mcp.json", "mcpServers"),
    ("zed", ".zed/settings.json", "context_servers"),
    ("codex", ".codex/config.toml", "mcp_servers"),
    ("opencode", "opencode.json", "mcp"),
    ("antigravity", ".agents/mcp_config.json", "mcpServers"),
    ("continue", ".continue/mcpServers/codenexus.json", "mcpServers"),
]


def _agent_type(value):
    from codenexus.wizard import AgentType

    return AgentType(value)


@pytest.mark.parametrize("agent,relpath,key", PROJECT_FILE_AGENTS)
def test_apply_config_project_writes_project_local_file(tmp_path, monkeypatch, agent, relpath, key):
    """apply_config_project writes <project>/<relpath> with the codenexus entry
    under the agent's correct top-level key, pointing at -w <project> serve."""
    at = _agent_type(agent)
    _stub_home_for(monkeypatch, tmp_path, at)
    from codenexus.wizard import AgentWizard

    proj = _make_repo(tmp_path, "alpha", "alpha_symbol")
    wiz = AgentWizard()
    assert wiz.apply_config_project(at, proj) is True

    pfile = proj / relpath
    assert pfile.exists(), f"project config file not written: {pfile}"
    text = pfile.read_text(encoding="utf-8")
    if relpath.endswith(".toml"):
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        data = tomllib.loads(text)
    else:
        data = json.loads(text)
    section = data[key]
    assert "codenexus" in section, f"codenexus not under {key} in {pfile}"
    entry = section["codenexus"]
    # OpenCode stores a `command` list; others use command + args.
    if "args" in entry:
        assert entry["args"] == ["-w", str(proj), "serve"], entry
    else:
        assert entry.get("command") == ["codenexus", "-w", str(proj), "serve"], entry


@pytest.mark.parametrize("agent,relpath,key", PROJECT_FILE_AGENTS)
def test_apply_config_project_preserves_existing_project_keys(tmp_path, monkeypatch, agent, relpath, key):
    """Merging the codenexus entry must keep existing keys in the project file."""
    at = _agent_type(agent)
    _stub_home_for(monkeypatch, tmp_path, at)
    from codenexus.wizard import AgentWizard

    proj = _make_repo(tmp_path, "alpha", "alpha_symbol")
    pfile = proj / relpath
    pfile.parent.mkdir(parents=True, exist_ok=True)
    if relpath.endswith(".toml"):
        pfile.write_text('other_key = "keep_me"\n', encoding="utf-8")
    else:
        pfile.write_text(json.dumps({"otherKey": {"keep": "me"}}), encoding="utf-8")

    wiz = AgentWizard()
    assert wiz.apply_config_project(at, proj) is True
    text = pfile.read_text(encoding="utf-8")
    if relpath.endswith(".toml"):
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        data = tomllib.loads(text)
        assert data.get("other_key") == "keep_me", "existing TOML key lost"
    else:
        data = json.loads(text)
        assert data["otherKey"] == {"keep": "me"}, "existing JSON key lost"
    assert "codenexus" in data[key], "codenexus not merged in"


UNSUPPORTED_AGENTS = ["windsurf", "augment", "openclaw", "hermes"]


@pytest.mark.parametrize("agent", UNSUPPORTED_AGENTS)
def test_apply_config_project_unsupported_agent(tmp_path, monkeypatch, capsys, agent):
    """Agents with no documented per-project mechanism must return False with a
    clear reason and write NO file."""
    at = _agent_type(agent)
    _stub_home_for(monkeypatch, tmp_path, at)
    from codenexus.wizard import AgentWizard

    proj = _make_repo(tmp_path, "alpha", "alpha_symbol")
    wiz = AgentWizard()
    result = wiz.apply_config_project(at, proj)
    assert result is False, f"{agent} must not get a per-project write"
    out = capsys.readouterr().out.lower()
    assert "not supported" in out, f"expected 'not supported' message for {agent}"
    # No project-local config file should have been created.
    leftover = [p for p in proj.rglob("*") if p.is_file() and p.name != "mod_alpha.py"]
    assert not leftover, f"unexpected file written for unsupported {agent}: {leftover}"


def test_apply_config_project_warns_on_global_shadow_project_agent(tmp_path, monkeypatch, capsys):
    """A global codenexus entry in the agent's GLOBAL config shadows the
    per-project one (agents merge global+project); warn loudly but still write."""
    at = _agent_type("cursor")
    gpath = _stub_home_for(monkeypatch, tmp_path, at)
    gpath.write_text(
        json.dumps({"mcpServers": {"codenexus": {"command": "codenexus", "args": ["-w", "/old", "serve"]}}}),
        encoding="utf-8",
    )
    from codenexus.wizard import AgentWizard

    proj = _make_repo(tmp_path, "alpha", "alpha_symbol")
    wiz = AgentWizard()
    assert wiz.apply_config_project(at, proj) is True

    out = capsys.readouterr().out
    assert "global" in out.lower() or "shadow" in out.lower(), "expected global-shadow warning"
    # Project file still written.
    pfile = proj / ".cursor" / "mcp.json"
    assert pfile.exists()
    data = json.loads(pfile.read_text(encoding="utf-8"))
    assert data["mcpServers"]["codenexus"]["args"] == ["-w", str(proj), "serve"]


def test_cli_setup_scope_local_writes_project_local_file(tmp_path, monkeypatch):
    """`wizard setup cursor --scope local -p <proj>` writes <proj>/.cursor/mcp.json."""
    from click.testing import CliRunner

    from codenexus.cli import main
    at = _agent_type("cursor")
    _stub_home_for(monkeypatch, tmp_path, at)

    proj = _make_repo(tmp_path, "alpha", "alpha_symbol")
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["wizard", "setup", "cursor", "--scope", "local", "--project", str(proj)],
        input="y\n",
    )
    assert result.exit_code == 0, result.output
    pfile = proj / ".cursor" / "mcp.json"
    assert pfile.exists(), "project config file not written via CLI"
    data = json.loads(pfile.read_text(encoding="utf-8"))
    assert data["mcpServers"]["codenexus"]["args"] == ["-w", str(proj), "serve"]


def test_interactive_setup_per_project_mode_3(tmp_path, monkeypatch):
    """Interactive wizard mode 3 (per-project local scope) writes the project-
    local config file, NOT the global one — independent per-project index.

    Regresses the gap where the interactive wizard only offered global (mode 1)
    and federated (mode 2), so the --scope local feature was unreachable from
    `codenexus wizard interactive`.
    """
    at = _agent_type("cursor")
    gpath = _stub_home_for(monkeypatch, tmp_path, at)
    from codenexus.wizard import AgentWizard

    proj = _make_repo(tmp_path, "alpha", "alpha_symbol")
    answers = iter(
        [
            "1",          # select first detected agent (cursor, monkeypatched)
            "3",          # per-project (local scope) mode
            str(proj),    # project path
            "y",          # apply
        ]
    )
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))

    wiz = AgentWizard()
    monkeypatch.setattr(wiz, "detect_installed_agents", lambda: [at])
    wiz.interactive_setup()

    # Project-local file written with the codenexus entry.
    pfile = proj / ".cursor" / "mcp.json"
    assert pfile.exists(), "interactive mode 3 must write the project-local config file"
    data = json.loads(pfile.read_text(encoding="utf-8"))
    assert data["mcpServers"]["codenexus"]["args"] == ["-w", str(proj), "serve"]
    # The GLOBAL config must NOT have been written — mode 3 is per-project, not global.
    assert not gpath.exists(), "interactive mode 3 must not write the global config"
