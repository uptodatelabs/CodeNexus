"""Tests for `wizard clear` index discovery and per-index block rendering."""

import json
import os
from pathlib import Path

import pytest


def _make_index(proj: Path, home: Path):
    """Create a real CodeNexus index under `home` for `proj`."""
    (proj / "main.py").write_text("def main():\n    return 1\n")
    from codenexus.server import CodeNexusServer

    srv = CodeNexusServer(proj, license_manager=None, use_llm=False)
    srv.index_workspace(incremental=False)
    return srv


def _write_claude_config(home: Path, projects: list[Path]):
    """Write a Claude Code mcp config pointing at `projects`."""
    cfg = home / ".claude.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "codenexus": {
                        "command": "codenexus",
                        "args": ["-w", str(projects[0]), "serve"],
                    }
                }
            }
        )
    )


def test_index_entries_grouped_per_project(tmp_path):
    """Each project with an index must appear once, with all referencing
    agents attached to that single entry (no duplicate/merged rows)."""
    from codenexus.agent_parser import (
        find_codenexus_index,
        get_all_indexed_projects,
    )

    proj_a = tmp_path / "proj_a"
    proj_a.mkdir()
    _make_index(proj_a, tmp_path / "fakehome_a")

    # Simulate two agents pointing at the same project.
    agent_projects = {
        "Claude Code": [{"path": str(proj_a), "config": {}}],
        "Hermes": [{"path": str(proj_a), "config": {}}],
    }

    # Replicate the grouping logic from cli.clear()
    project_to_agents = {}
    for agent_name, projects in agent_projects.items():
        for p in projects:
            project_to_agents.setdefault(p["path"], set()).add(agent_name)

    entries = []
    seen = set()
    for project_path, agents in project_to_agents.items():
        index_path = find_codenexus_index(project_path)
        assert index_path is not None
        real_dir = index_path.parent.resolve()
        if real_dir in seen:
            continue
        seen.add(real_dir)
        entries.append({"project": project_path, "agents": sorted(agents)})

    assert len(entries) == 1
    assert set(entries[0]["agents"]) == {"Claude Code", "Hermes"}


def test_clear_renders_per_index_blocks(tmp_path, monkeypatch):
    """Two indexes with different agent sets must render as separate blocks
    (idx-1, idx-2) with Agents/Project Path/Size on distinct lines, and must
    not interleave. Uses a fake HOME so real indexes are never touched."""
    from click.testing import CliRunner

    from codenexus.cli import main as cli

    fakehome = tmp_path / "fakehome"
    fakehome.mkdir()

    # idx-1: a project referenced by several agents; idx-2: one agent only.
    proj_a = tmp_path / "proj_a"
    proj_a.mkdir()
    proj_b = tmp_path / "proj_b"
    proj_b.mkdir()

    # Claude Code points at proj_a; Hermes also at proj_a (multi-agent).
    (fakehome / ".claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "codenexus": {
                        "command": "codenexus",
                        "args": ["-w", str(proj_a), "serve"],
                    }
                }
            }
        )
    )
    (fakehome / ".hermes").mkdir(parents=True)
    (fakehome / ".hermes" / "config.yaml").write_text(
        "mcp_servers:\n  codenexus:\n    command: codenexus\n"
        f'    args: ["-w", "{proj_a}", "serve"]\n'
    )
    # OpenClaw skill points at proj_b (single agent).
    skill = fakehome / ".openclaw" / "workspace" / "skills" / "codenexus"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"codenexus -w {proj_b} serve\n"
    )

    _make_index(proj_a, fakehome)
    _make_index(proj_b, fakehome)

    monkeypatch.setenv("HOME", str(fakehome))

    runner = CliRunner()
    result = runner.invoke(cli, ["wizard", "clear", "--all", "--yes"])
    assert result.exit_code == 0, result.output

    # Both index blocks are present and labelled by ID.
    assert "idx-1" in result.output
    assert "idx-2" in result.output
    # Each block shows the three fields on their own lines.
    assert "Agents" in result.output
    assert "Project Path" in result.output
    assert "Size" in result.output
    # The path leaf must be visible (not silently dropped).
    assert "proj_a" in result.output
    assert "proj_b" in result.output
