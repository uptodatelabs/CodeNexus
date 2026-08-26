"""Tests for wizard clear: index discovery, agent merging, and rendering."""

import json
from pathlib import Path


def _make_index(proj: Path, home: Path):
    """Create a real CodeNexus index under `home` for `proj`."""
    (proj / "main.py").write_text("def main():\n    return 1\n")
    from codenexus.server import CodeNexusServer

    srv = CodeNexusServer(proj, license_manager=None, use_llm=False)
    srv.index_workspace(incremental=False)
    return srv


def _write_agent_configs(home: Path, paths: dict[str, Path]):
    """Write agent configs. `paths` maps agent name -> project path."""
    if "claude" in paths:
        cfg = home / ".claude.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "codenexus": {
                            "command": "codenexus",
                            "args": ["-w", str(paths["claude"]), "serve"],
                        }
                    }
                }
            )
        )
    if "hermes" in paths:
        (home / ".hermes").mkdir(parents=True, exist_ok=True)
        (home / ".hermes" / "config.yaml").write_text(
            "mcp_servers:\n  codenexus:\n    command: codenexus\n"
            f'    args: ["-w", "{paths["hermes"]}", "serve"]\n'
        )
    if "opencode" in paths:
        (home / ".config" / "opencode").mkdir(parents=True, exist_ok=True)
        (home / ".config" / "opencode" / "opencode.jsonc").write_text(
            json.dumps(
                {
                    "mcp": {
                        "codenexus": {
                            "type": "local",
                            "command": [
                                "codenexus",
                                "-w",
                                str(paths["opencode"]),
                                "serve",
                            ],
                        }
                    }
                }
            )
        )
    if "antigravity" in paths:
        (home / ".gemini" / "config").mkdir(parents=True, exist_ok=True)
        (home / ".gemini" / "config" / "mcp_config.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "codenexus": {
                            "command": "codenexus",
                            "args": ["-w", str(paths["antigravity"]), "serve"],
                        }
                    }
                }
            )
        )
    if "openclaw" in paths:
        skill = home / ".openclaw" / "workspace" / "skills" / "codenexus"
        skill.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text(f"codenexus -w {paths['openclaw']} serve\n")


def test_find_index_walks_down_from_ancestor(tmp_path):
    """An agent config pointing at a PARENT dir must still locate the index
    that lives in a child project dir (walk-down)."""
    from codenexus.agent_parser import find_codenexus_index

    parent = tmp_path / "parent"
    proj = parent / "myproject"
    proj.mkdir(parents=True)
    _make_index(proj, tmp_path / "home_a")

    found = find_codenexus_index(str(parent))
    assert found is not None
    assert found.parent == (proj / ".codenexus")


def test_find_index_exact_root(tmp_path):
    """An agent config pointing exactly at the project root is found."""
    from codenexus.agent_parser import find_codenexus_index

    proj = tmp_path / "proj"
    proj.mkdir()
    _make_index(proj, tmp_path / "home_b")

    found = find_codenexus_index(str(proj))
    assert found is not None
    assert found.parent == (proj / ".codenexus")


def test_clear_merges_agents_same_index(tmp_path, monkeypatch):
    """When several agents reference the same index (possibly via parent vs
    exact paths), clear() must show them TOGETHER in one block, not drop any."""
    from click.testing import CliRunner

    from codenexus.cli import main as cli

    fakehome = tmp_path / "fakehome"
    fakehome.mkdir()

    proj_a = tmp_path / "proj_a"
    proj_a.mkdir()
    _make_index(proj_a, fakehome)

    # claude/hermes point AT proj_a; opencode points at its PARENT (tmp_path).
    # All three must land in the same idx block.
    _write_agent_configs(
        fakehome,
        {"claude": proj_a, "hermes": proj_a, "opencode": tmp_path},
    )

    monkeypatch.setenv("HOME", str(fakehome))

    runner = CliRunner()
    result = runner.invoke(cli, ["wizard", "clear", "--all", "--yes"])
    assert result.exit_code == 0, result.output

    assert "idx-1" in result.output
    assert "Claude Code" in result.output
    assert "Hermes" in result.output
    assert "OpenCode" in result.output
    # OpenClaw not configured here, so must NOT appear.
    assert "OpenClaw" not in result.output


def test_clear_warns_unindexed_agent(tmp_path, monkeypatch):
    """An agent whose configured path has NO index must appear in a warning
    (not silently vanish), so the user knows why it's absent from the table."""
    from click.testing import CliRunner

    from codenexus.cli import main as cli

    fakehome = tmp_path / "fakehome"
    fakehome.mkdir()

    proj_a = tmp_path / "proj_a"
    proj_a.mkdir()
    _make_index(proj_a, fakehome)

    # claude points at the indexed proj_a; opencode points at a path with no
    # index (proj_b, never indexed).
    proj_b = tmp_path / "proj_b"
    proj_b.mkdir()
    _write_agent_configs(fakehome, {"claude": proj_a, "opencode": proj_b})

    monkeypatch.setenv("HOME", str(fakehome))

    runner = CliRunner()
    result = runner.invoke(cli, ["wizard", "clear", "--all", "--yes"])
    assert result.exit_code == 0, result.output
    # Indexed agent shows in the table.
    assert "Claude Code" in result.output
    # Unindexed agent is called out in the warning, not dropped silently.
    assert "Warning" in result.output
    assert "OpenCode" in result.output
    assert "no index found" in result.output


def test_clear_separates_distinct_indexes(tmp_path, monkeypatch):
    """Two different indexes must appear as two separate blocks."""
    from click.testing import CliRunner

    from codenexus.cli import main as cli

    fakehome = tmp_path / "fakehome"
    fakehome.mkdir()

    proj_a = tmp_path / "proj_a"
    proj_a.mkdir()
    proj_b = tmp_path / "proj_b"
    proj_b.mkdir()
    _make_index(proj_a, fakehome)
    _make_index(proj_b, fakehome)

    _write_agent_configs(fakehome, {"claude": proj_a, "openclaw": proj_b})

    monkeypatch.setenv("HOME", str(fakehome))

    runner = CliRunner()
    result = runner.invoke(cli, ["wizard", "clear", "--all", "--yes"])
    assert result.exit_code == 0, result.output
    assert "idx-1" in result.output
    assert "idx-2" in result.output
    assert "proj_a" in result.output
    assert "proj_b" in result.output


def test_clear_all_five_agents_neutral_domains(tmp_path, monkeypatch):
    """GENERIC verification (no trading/Github assumptions): five agents, each
    pointing at a DIFFERENT project under neutral paths, must all appear as
    separate blocks. Covers Flow1/2/3 in one scenario with non-code domains."""
    from click.testing import CliRunner

    from codenexus.cli import main as cli

    fakehome = tmp_path / "fakehome"
    fakehome.mkdir()

    # Neutral, non-codebase project names (proves the tool is domain-agnostic).
    projects = {
        "novel": tmp_path / "my_novel",
        "photos": tmp_path / "photo_lib",
        "music": tmp_path / "track_repo",
        "docs": tmp_path / "writing",
        "data": tmp_path / "dataset",
    }
    for p in projects.values():
        p.mkdir()
        _make_index(p, fakehome)

    _write_agent_configs(
        fakehome,
        {
            "claude": projects["novel"],
            "hermes": projects["photos"],
            "opencode": projects["music"],
            "antigravity": projects["docs"],
            "openclaw": projects["data"],
        },
    )

    monkeypatch.setenv("HOME", str(fakehome))

    runner = CliRunner()
    result = runner.invoke(cli, ["wizard", "clear", "--all", "--yes"])
    assert result.exit_code == 0, result.output
    # All five leaves present, one block each.
    for name in ("my_novel", "photo_lib", "track_repo", "writing", "dataset"):
        assert name in result.output, f"missing block for {name}"
    # All five agent names present (no silent drop).
    for name in ("Claude Code", "Hermes", "OpenCode", "Antigravity", "OpenClaw"):
        assert name in result.output, f"missing agent {name}"


def test_clear_parent_child_paths_neutral(tmp_path, monkeypatch):
    """Flow3 (parent/child): an agent at a PARENT dir and another at its CHILD
    must stay as two distinct blocks, not merged. Neutral paths."""
    from click.testing import CliRunner

    from codenexus.cli import main as cli

    fakehome = tmp_path / "fakehome"
    fakehome.mkdir()

    parent = tmp_path / "workspace"
    child = parent / "subproject"
    child.mkdir(parents=True)
    _make_index(parent, fakehome)
    _make_index(child, fakehome)

    _write_agent_configs(
        fakehome,
        {"claude": parent, "opencode": child},
    )

    monkeypatch.setenv("HOME", str(fakehome))

    runner = CliRunner()
    result = runner.invoke(cli, ["wizard", "clear", "--all", "--yes"])
    assert result.exit_code == 0, result.output
    assert "idx-1" in result.output
    assert "idx-2" in result.output
    # Parent and child must NOT be merged into one block.
    assert "workspace" in result.output
    assert "subproject" in result.output


def test_clear_missing_config_file_no_crash(tmp_path, monkeypatch):
    """Flow1 edge: one agent's config file is deleted entirely. The remaining
    configured agents must still list, and no crash occurs."""
    from click.testing import CliRunner

    from codenexus.cli import main as cli

    fakehome = tmp_path / "fakehome"
    fakehome.mkdir()

    proj_a = tmp_path / "proj_a"
    proj_a.mkdir()
    proj_b = tmp_path / "proj_b"
    proj_b.mkdir()
    _make_index(proj_a, fakehome)
    _make_index(proj_b, fakehome)

    # Only claude configured; hermes/opencode files absent.
    _write_agent_configs(fakehome, {"claude": proj_a, "opencode": proj_b})

    monkeypatch.setenv("HOME", str(fakehome))

    runner = CliRunner()
    result = runner.invoke(cli, ["wizard", "clear", "--all", "--yes"])
    assert result.exit_code == 0, result.output
    assert "Claude Code" in result.output
    assert "OpenCode" in result.output
    # No traceback / exception text leaked.
    assert "Traceback" not in result.output
    assert "Error" not in result.output
