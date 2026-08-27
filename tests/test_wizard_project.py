"""Wizard per-project (local-scope) registration: one agent, independent
indexes per project, stored in Claude Code's ``projects`` map in ~/.claude.json.

Tests are written against the intended public API before the implementation
exists (red), then driven green.
"""

import json


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
