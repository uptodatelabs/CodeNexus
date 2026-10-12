"""Red reproduction for B1 (impact mis-resolution) and B2 (multi-word search)."""
from pathlib import Path


def _make_ws(tmp_path: Path):
    from codenexus.server import CodeNexusServer

    (tmp_path / "pkg").mkdir(exist_ok=True)
    (tmp_path / "pkg" / "core.py").write_text(
        "class Engine:\n    def run(self, x):\n        return x * 2\n\n"
        "def helper(v):\n    return Engine().run(v)\n"
    )
    (tmp_path / "pkg" / "app.py").write_text(
        "from pkg.core import helper\n\ndef main():\n    return helper(21)\n"
    )
    srv = CodeNexusServer(tmp_path)
    srv.index_workspace(incremental=False)
    return srv


def test_b2_multiword_search_returns_results(tmp_path):
    srv = _make_ws(tmp_path)
    try:
        hits = srv.graph.search_nodes("helper function", limit=5)
        names = [n.name for n in hits]
        assert "helper" in names, f"multi-word query returned {names}"
    finally:
        srv.graph.close()


def test_b1_impact_resolves_exact_symbol(tmp_path):
    from click.testing import CliRunner

    from codenexus.cli import main as cli

    srv = _make_ws(tmp_path)
    srv.graph.close()
    runner = CliRunner()
    result = runner.invoke(cli, ["--workspace", str(tmp_path), "impact", "Engine", "--depth", "2"])
    assert result.exit_code == 0, result.output
    # Must resolve to the Engine class, not to helper().
    assert "Impact Analysis: Engine" in result.output, result.output
