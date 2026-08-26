"""Productization tests: pipeline rendering, license gating, and DRY."""

import asyncio
import json
import subprocess

import pytest


@pytest.fixture
def sample_project(tmp_path):
    """Create an indexable project and index it."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "auth.py").write_text(
        "def login(user):\n    return user.token\n\n"
        "def authenticate(req):\n    return req.ok\n"
    )
    (proj / "main.go").write_text(
        "package main\n\nfunc main() {\n    login()\n}\n"
    )
    subprocess.run(
        ["codenexus", "-w", str(proj), "index"],
        check=True,
        capture_output=True,
    )
    return proj


# --------------------------------------------------------------------------- #
# 항목 1: pipeline 출력은 구조화된 텍스트 (이스케이프 JSON 박제 아님)
# --------------------------------------------------------------------------- #
def test_pipeline_output_is_structured(tmp_path, sample_project, cli_runner):
    """CLI `pipeline` must print human-readable sections, not raw JSON text."""
    from codenexus.cli import main

    result = cli_runner.invoke(
        main, ["-w", str(sample_project), "pipeline", "fix login bug"]
    )
    out = result.output

    # The old behaviour printed an escaped-JSON blob: { "task": ... }
    # New behaviour prints labelled sections.
    assert "Task:" in out
    assert '"task":' not in out, "raw escaped JSON must not be printed"
    # intent is produced now that LLM gating feeds the pipeline
    assert "Detected intent:" in out
    assert "Token estimate:" in out


def test_pipeline_data_shape(tmp_path):
    """`_pipeline_data` returns the structured dict consumed by the renderer."""
    from codenexus.server import CodeNexusServer

    eng = CodeNexusServer(tmp_path)
    data = eng._pipeline_data({"task": "fix login", "max_tokens": 8000})
    assert data["task"] == "fix login"
    assert "intent" in data
    assert "pivot_files" in data
    assert "skeletons" in data
    assert isinstance(data["token_estimate"], int)


# --------------------------------------------------------------------------- #
# 항목 2: fully open source — every feature enabled unconditionally
# --------------------------------------------------------------------------- #
@pytest.fixture
def cli_runner():
    from click.testing import CliRunner

    return CliRunner()


def test_all_languages_enabled(tmp_path):
    """Open source: all seven languages index without any gating."""
    from codenexus.server import CodeNexusServer

    eng = CodeNexusServer(tmp_path)
    for lang in ("python", "javascript", "typescript", "go", "rust", "java", "csharp"):
        assert eng.is_language_enabled(lang)
    assert eng.max_nodes_limit is None
    assert eng.memory_enabled is True


def test_memory_enabled_by_default(tmp_path):
    """Session memory is available to everyone."""
    from codenexus.server import CodeNexusServer

    eng = CodeNexusServer(tmp_path)
    assert eng.memory is not None
    session_id = eng.start_session("x")
    assert isinstance(session_id, str) and session_id


def test_indexing_has_no_language_filter(monkeypatch, tmp_path):
    """Indexing parses every supported language."""
    from codenexus.server import CodeNexusServer

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("def f():\n    return 1\n")
    (proj / "b.go").write_text("package main\nfunc g() {}\n")

    eng = CodeNexusServer(proj)
    count = eng.index_workspace()
    assert count == 2
    go_nodes = eng.graph.conn.execute(
        "SELECT COUNT(*) FROM nodes WHERE file_path LIKE '%.go'"
    ).fetchone()[0]
    assert go_nodes > 0


def test_workspace_accepts_multiple_repos(tmp_path):
    """Multi-repo workspaces have no repository cap."""
    from codenexus.workspace import MultiRepoWorkspace

    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    for n in ("r1", "r2", "r3"):
        (tmp_path / n).mkdir()
        (tmp_path / n / "m.py").write_text("def f():\n    pass\n")

    ws = MultiRepoWorkspace(ws_dir)
    for n in ("r1", "r2", "r3"):
        assert ws.add_repo(n, tmp_path / n)


# --------------------------------------------------------------------------- #
# DRY: mcp_server reuses the engine (no duplicated pipeline logic)
# --------------------------------------------------------------------------- #
def test_mcp_server_uses_engine_dispatch(sample_project):
    """The MCP transport must return real results via the shared engine."""
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command="codenexus",
        args=["-w", str(sample_project), "serve"],
    )

    async def call():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool(
                    "run_pipeline",
                    {"task": "fix login", "max_tokens": 2000},
                )
                text = res.content[0].text  # type: ignore[union-attr]
                return json.loads(text)

    result = asyncio.run(call())
    assert "pivot_files" in result or "skeletons" in result
    assert result["task"] == "fix login"


def test_list_tools_single_source(sample_project):
    """list_tool_definitions must be the single tool registry."""
    from codenexus.server import CodeNexusServer

    eng = CodeNexusServer(sample_project)
    tools = eng.list_tool_definitions()
    names = {t.name for t in tools}
    assert names == {"run_pipeline", "get_context_capsule", "get_skeleton", "index_status"}
