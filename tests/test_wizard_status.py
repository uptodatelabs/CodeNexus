"""Wizard status: per-index Nodes/Files/Edges + token savings + compression.

Tests are written against the intended public API before the implementation
exists (red), then driven green.

Token model (structural, query-independent):
  full_tokens     = Σ len(node.content.split()) * 1.3   — cost of sending all
                    indexed source to a model.
  skeleton_tokens = Σ len(node.signature.split()) * 1.3 — the compressed
                    signature-only form CodeNexus serves for retrieval.
  savings_tokens  = full - skeleton
  compression_pct = (1 - skeleton/full) * 100
"""

import json
from pathlib import Path


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
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


def _index_single(proj: Path):
    """Build a real single-project CodeNexus index under proj/.codenexus."""
    from codenexus.server import CodeNexusServer

    srv = CodeNexusServer(proj, license_manager=None, use_llm=False)
    srv.index_workspace(incremental=False)
    # Release sqlite handles so read-only reopen and tmp cleanup are clean.
    if getattr(srv, "memory", None):
        srv.memory.close()
        srv.memory = None
    srv.graph.close()
    return proj / ".codenexus"


def _write_claude_config(home: Path, project: Path):
    cfg = home / ".claude.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "codenexus": {
                        "command": "codenexus",
                        "args": ["-w", str(project), "serve"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# compute_index_stats: single-project index
# --------------------------------------------------------------------------- #
def test_compute_index_stats_single(tmp_path):
    from codenexus.agent_parser import compute_index_stats

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "mod.py").write_text(
        "def alpha():\n    return 'a'\n\n\ndef beta(x):\n    return x + 1\n",
        encoding="utf-8",
    )
    index_dir = _index_single(proj)

    stats = compute_index_stats(index_dir)
    assert stats is not None, "no stats returned for a valid single index"
    assert stats["dbs"] == 1
    assert stats["nodes"] >= 2
    assert stats["files"] >= 1
    assert stats["edges"] >= 0
    # Full source is larger than the signature-only skeleton form.
    assert stats["full_tokens"] > 0
    assert stats["skeleton_tokens"] > 0
    assert stats["full_tokens"] > stats["skeleton_tokens"]
    assert stats["savings_tokens"] == stats["full_tokens"] - stats["skeleton_tokens"]
    assert 0 < stats["compression_pct"] <= 100


def test_compute_index_stats_missing_db(tmp_path):
    """An index dir with no DB must return None, not raise."""
    from codenexus.agent_parser import compute_index_stats

    empty = tmp_path / "noindex"
    empty.mkdir()
    assert compute_index_stats(empty) is None


# --------------------------------------------------------------------------- #
# compute_index_stats: multi-repo workspace index
# --------------------------------------------------------------------------- #
def test_compute_index_stats_multi_repo(tmp_path, monkeypatch):
    from codenexus.agent_parser import compute_index_stats
    from codenexus.wizard import AgentType, AgentWizard

    _fake_home(monkeypatch, tmp_path)

    ws_root = tmp_path / "ws"
    repo_a = _make_repo(tmp_path, "alpha", "alpha_symbol")
    repo_b = _make_repo(tmp_path, "beta", "beta_symbol")
    AgentWizard().apply_config_multi(
        AgentType.CLAUDE_CODE, ws_root, [("alpha", repo_a), ("beta", repo_b)]
    )

    stats = compute_index_stats(ws_root / ".codenexus")
    assert stats is not None
    # Two member DBs aggregated into one stats block.
    assert stats["dbs"] == 2
    assert stats["nodes"] >= 2
    assert stats["full_tokens"] > stats["skeleton_tokens"]
    assert 0 < stats["compression_pct"] <= 100


# --------------------------------------------------------------------------- #
# CLI: codenexus wizard status [project_path]
# --------------------------------------------------------------------------- #
def test_wizard_status_with_project_path(tmp_path):
    from click.testing import CliRunner

    from codenexus.cli import main

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "mod.py").write_text("def alpha():\n    return 'a'\n", encoding="utf-8")
    _index_single(proj)

    runner = CliRunner()
    result = runner.invoke(main, ["wizard", "status", str(proj)])
    assert result.exit_code == 0, result.output
    assert "Nodes:" in result.output
    assert "Token savings:" in result.output
    assert "Files:" in result.output


def test_wizard_status_no_index(tmp_path):
    """Pointing status at a project with no index must exit cleanly with a note."""
    from click.testing import CliRunner

    from codenexus.cli import main

    proj = tmp_path / "empty"
    proj.mkdir()

    runner = CliRunner()
    result = runner.invoke(main, ["wizard", "status", str(proj)])
    assert result.exit_code == 0, result.output
    assert "No CodeNexus index" in result.output


def test_wizard_status_discovers_all(tmp_path, monkeypatch):
    """With no path arg, status discovers all agent-referenced indexes (like clear)."""
    from click.testing import CliRunner

    from codenexus.cli import main

    fakehome = _fake_home(monkeypatch, tmp_path)

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "mod.py").write_text("def alpha():\n    return 'a'\n", encoding="utf-8")
    _index_single(proj)
    _write_claude_config(fakehome, proj)

    runner = CliRunner()
    result = runner.invoke(main, ["wizard", "status"])
    assert result.exit_code == 0, result.output
    assert "idx-1" in result.output
    assert "Claude Code" in result.output
    assert "Token savings:" in result.output
