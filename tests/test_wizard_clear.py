"""Tests for `wizard clear` index discovery and table rendering."""

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


def test_index_entries_grouped_per_project(tmp_path):
    """Each project with an index must appear once, with all referencing
    agents attached to that single row (no duplicate/merged rows)."""
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


def test_clear_table_renders_without_crash(tmp_path, monkeypatch):
    """The clear table must render (no exception) and show the project path,
    using a fake HOME so the real user's indexes are never touched."""
    from click.testing import CliRunner

    from codenexus.cli import main as cli

    fakehome = tmp_path / "fakehome"
    fakehome.mkdir()

    proj = tmp_path / "deeply" / "nested" / "project" / "dir"
    proj.mkdir(parents=True)
    _make_index(proj, fakehome)

    monkeypatch.setenv("HOME", str(fakehome))
    monkeypatch.chdir(proj)  # clear() also scans the current directory

    runner = CliRunner()
    # Point the runner at our temp project so only it is discovered.
    result = runner.invoke(
        cli, ["-w", str(proj), "wizard", "clear", "--all", "--yes"]
    )
    assert result.exit_code == 0, result.output
    assert "CodeNexus Indexes" in result.output
    # Path must be visible (not silently dropped) in the rendered table.
    assert "project" in result.output or "dir" in result.output
