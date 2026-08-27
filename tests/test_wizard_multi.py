"""Wizard multi-repo registration: one agent, many indexes.

Verifies the convenience flow that lets a user register several repos with a
single agent through the wizard (interactive + CLI) and have them served by
one MCP registration via a federated workspace.

Tests are written against the intended public API before the implementation
exists (red), then driven green.
"""

import json
from pathlib import Path


def _fake_home(monkeypatch, tmp_path):
    """Point HOME/USERPROFILE at a tmp dir so ~/.claude.json lands there."""
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
# apply_config_multi: the core engine
# --------------------------------------------------------------------------- #
def test_apply_config_multi_creates_workspace_with_member_repos(tmp_path, monkeypatch):
    """apply_config_multi must create a workspace.json registering every repo."""
    _fake_home(monkeypatch, tmp_path)
    from codenexus.wizard import AgentType, AgentWizard

    ws_root = tmp_path / "ws"
    repo_a = _make_repo(tmp_path, "alpha", "alpha_symbol")
    repo_b = _make_repo(tmp_path, "beta", "beta_symbol")

    wiz = AgentWizard()
    ok = wiz.apply_config_multi(
        AgentType.CLAUDE_CODE, ws_root, [("alpha", repo_a), ("beta", repo_b)]
    )
    assert ok

    ws_json = ws_root / ".codenexus" / "workspace.json"
    assert ws_json.exists(), "workspace.json was not created"
    data = json.loads(ws_json.read_text(encoding="utf-8"))
    aliases = {r["alias"] for r in data["repos"]}
    assert aliases == {"alpha", "beta"}, aliases


def test_apply_config_multi_indexes_every_member(tmp_path, monkeypatch):
    """Each member repo must be indexed (a .db per alias) and queryable."""
    _fake_home(monkeypatch, tmp_path)
    from codenexus.wizard import AgentType, AgentWizard

    ws_root = tmp_path / "ws"
    repo_a = _make_repo(tmp_path, "alpha", "alpha_symbol")
    repo_b = _make_repo(tmp_path, "beta", "beta_symbol")

    AgentWizard().apply_config_multi(
        AgentType.CLAUDE_CODE, ws_root, [("alpha", repo_a), ("beta", repo_b)]
    )

    # Per-member index DBs exist.
    assert (ws_root / ".codenexus" / "repos" / "alpha.db").exists()
    assert (ws_root / ".codenexus" / "repos" / "beta.db").exists()

    # Serving the workspace root exposes BOTH repos through one registration.
    import asyncio

    from codenexus.server import CodeNexusServer

    srv = CodeNexusServer(ws_root)
    try:
        assert srv._federated is not None
        st = json.loads(asyncio.run(srv.dispatch_tool("index_status", {}))[0].text)
        assert st["mode"] == "multi-repo"
        assert {r["alias"] for r in st["repos"]} == {"alpha", "beta"}
        cap = json.loads(
            asyncio.run(
                srv.dispatch_tool("get_context_capsule", {"query": "symbol", "max_tokens": 2000})
            )[0].text
        )
        blob = json.dumps(cap, ensure_ascii=False)
        assert "alpha" in blob and "beta" in blob
    finally:
        if srv._federated:
            srv._federated.close()


def test_apply_config_multi_writes_agent_config_pointing_at_workspace(tmp_path, monkeypatch):
    """The agent config must reference the workspace root (one registration)."""
    fakehome = _fake_home(monkeypatch, tmp_path)
    from codenexus.wizard import AgentType, AgentWizard

    ws_root = tmp_path / "ws"
    repo_a = _make_repo(tmp_path, "alpha", "alpha_symbol")

    AgentWizard().apply_config_multi(
        AgentType.CLAUDE_CODE, ws_root, [("alpha", repo_a)]
    )

    cfg = json.loads((fakehome / ".claude.json").read_text(encoding="utf-8"))
    args = cfg["mcpServers"]["codenexus"]["args"]
    assert "-w" in args
    w_idx = args.index("-w")
    # The -w path must be the workspace root, not the member repo.
    assert Path(args[w_idx + 1]).resolve() == ws_root.resolve()
    assert "serve" in args


def test_apply_config_multi_appends_to_existing_workspace(tmp_path, monkeypatch):
    """Re-running with the same workspace root must add repos, not wipe them."""
    _fake_home(monkeypatch, tmp_path)
    from codenexus.wizard import AgentType, AgentWizard

    ws_root = tmp_path / "ws"
    repo_a = _make_repo(tmp_path, "alpha", "alpha_symbol")
    AgentWizard().apply_config_multi(AgentType.CLAUDE_CODE, ws_root, [("alpha", repo_a)])

    repo_b = _make_repo(tmp_path, "beta", "beta_symbol")
    AgentWizard().apply_config_multi(AgentType.CLAUDE_CODE, ws_root, [("beta", repo_b)])

    data = json.loads((ws_root / ".codenexus" / "workspace.json").read_text(encoding="utf-8"))
    assert {r["alias"] for r in data["repos"]} == {"alpha", "beta"}


# --------------------------------------------------------------------------- #
# CLI: codenexus wizard setup-workspace
# --------------------------------------------------------------------------- #
def test_cli_setup_workspace_creates_workspace_and_config(tmp_path, monkeypatch):
    """`wizard setup-workspace <agent> --repo ALIAS=PATH ...` end-to-end."""
    _fake_home(monkeypatch, tmp_path)
    from click.testing import CliRunner

    from codenexus.cli import main

    repo_a = _make_repo(tmp_path, "alpha", "alpha_symbol")
    repo_b = _make_repo(tmp_path, "beta", "beta_symbol")
    ws_root = tmp_path / "ws"

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "wizard",
            "setup-workspace",
            "claude",
            "--workspace-root",
            str(ws_root),
            "--repo",
            f"alpha={repo_a}",
            "--repo",
            f"beta={repo_b}",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (ws_root / ".codenexus" / "workspace.json").exists()
    data = json.loads((ws_root / ".codenexus" / "workspace.json").read_text(encoding="utf-8"))
    assert {r["alias"] for r in data["repos"]} == {"alpha", "beta"}
    # Agent config also written.
    fakehome = Path(tmp_path / "fakehome")
    cfg = json.loads((fakehome / ".claude.json").read_text(encoding="utf-8"))
    assert "codenexus" in cfg["mcpServers"]


def test_cli_setup_workspace_requires_at_least_one_repo(tmp_path, monkeypatch):
    """No --repo => clear error, no workspace created."""
    _fake_home(monkeypatch, tmp_path)
    from click.testing import CliRunner

    from codenexus.cli import main

    ws_root = tmp_path / "ws"
    runner = CliRunner()
    result = runner.invoke(
        main, ["wizard", "setup-workspace", "claude", "--workspace-root", str(ws_root)]
    )
    assert result.exit_code != 0
    assert not (ws_root / ".codenexus" / "workspace.json").exists()


# --------------------------------------------------------------------------- #
# Interactive wizard: multi-repo mode
# --------------------------------------------------------------------------- #
def test_interactive_setup_multi_mode(tmp_path, monkeypatch):
    """Interactive wizard mode 2 builds a multi-repo workspace + agent config."""
    fakehome = _fake_home(monkeypatch, tmp_path)
    from codenexus.wizard import AgentType, AgentWizard

    repo_a = _make_repo(tmp_path, "alpha", "alpha_symbol")
    repo_b = _make_repo(tmp_path, "beta", "beta_symbol")
    ws_root = tmp_path / "ws"

    answers = iter(
        [
            "1",            # select first detected agent (claude, monkeypatched)
            "2",            # multi-repo mode
            str(ws_root),   # workspace root
            "",             # workspace name (default)
            str(repo_a),    # repo 1 path
            "alpha",        # repo 1 alias
            str(repo_b),    # repo 2 path
            "beta",         # repo 2 alias
            "",             # empty path => finish
            "y",            # apply
        ]
    )
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))

    wiz = AgentWizard()
    # Force a detected agent even though none is installed in the test env.
    monkeypatch.setattr(wiz, "detect_installed_agents", lambda: [AgentType.CLAUDE_CODE])
    wiz.interactive_setup()

    assert (ws_root / ".codenexus" / "workspace.json").exists()
    data = json.loads((ws_root / ".codenexus" / "workspace.json").read_text(encoding="utf-8"))
    assert {r["alias"] for r in data["repos"]} == {"alpha", "beta"}
    cfg = json.loads((fakehome / ".claude.json").read_text(encoding="utf-8"))
    assert "codenexus" in cfg["mcpServers"]


def test_interactive_multi_does_not_promise_empty_to_finish_on_first_repo(
    tmp_path, monkeypatch, capsys
):
    """First repo prompt must not say 'empty path to finish' — you can't finish
    with zero repos. Regresses the trap where the user pressed Enter (as the
    header instructed) and got an 'Add at least one repository' error loop with
    no way forward.

    Feeds a LEADING empty path (exactly what the user did), then a real repo,
    then finishes. Asserts the guidance shown before the first repo does not
    promise empty-to-finish, and that the flow recovers and registers the repo.
    """
    fakehome = _fake_home(monkeypatch, tmp_path)
    from codenexus.wizard import AgentType, AgentWizard

    repo_a = _make_repo(tmp_path, "alpha", "alpha_symbol")
    ws_root = tmp_path / "ws"

    answers = iter(
        [
            "1",            # agent (claude, monkeypatched)
            "2",            # multi-repo mode
            str(ws_root),   # workspace root
            "",             # workspace name (default)
            "",             # repo path EMPTY (leading) -> must error+reprompt, NOT finish
            str(repo_a),    # repo path (now valid)
            "alpha",        # alias
            "",             # empty path -> finish (now legitimate: 1 repo added)
            "y",            # apply
        ]
    )
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))

    wiz = AgentWizard()
    monkeypatch.setattr(wiz, "detect_installed_agents", lambda: [AgentType.CLAUDE_CODE])
    wiz.interactive_setup()

    out = capsys.readouterr().out

    # Guidance shown before the first repo (text up to the first ERROR) must
    # NOT promise 'empty path to finish' — that is a lie when no repo is added.
    err_idx = out.find("[ERROR]")
    assert err_idx != -1, "expected an error for the leading empty path"
    pre_error = out[:err_idx]
    assert "empty path to finish" not in pre_error, (
        "first-repo guidance must not offer empty-path-to-finish (zero repos cannot finish)"
    )

    # The flow recovered from the leading empty and registered the repo.
    assert (ws_root / ".codenexus" / "workspace.json").exists()
    data = json.loads((ws_root / ".codenexus" / "workspace.json").read_text(encoding="utf-8"))
    assert {r["alias"] for r in data["repos"]} == {"alpha"}
    cfg = json.loads((fakehome / ".claude.json").read_text(encoding="utf-8"))
    assert "codenexus" in cfg["mcpServers"]
