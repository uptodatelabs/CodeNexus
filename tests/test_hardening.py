"""Regression suite for hardening v1.2.

Covers the defects found in the full codebase audit: Node row mapping,
edge duplication, FTS synchronization, PageRank validity via import
resolution, parser robustness (CJK/BOM/constructors), MCP protocol
compliance, CLI regressions, session-memory robustness, license gating,
and wizard config-write safety.
"""

import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from codenexus.graph import DependencyGraph, Edge, Node
from codenexus.memory import DecisionType, get_memory
from codenexus.parser import CodeParser, detect_language
from codenexus.resolver import FileEntry, ImportResolver


def _node(nid, name="fn", ntype="function"):
    return Node(
        id=nid,
        file_path=nid.split("::")[0],
        name=name,
        node_type=ntype,
        start_line=0,
        end_line=1,
        content=f"{ntype} {name}",
        signature=f"{ntype} {name}()",
    )


@pytest.fixture
def graph(temp_dir):
    db_path = temp_dir / "harden.db"
    g = DependencyGraph(db_path)
    yield g
    g.close()


# ---------------------------------------------------------------------------
# Graph integrity
# ---------------------------------------------------------------------------

def test_node_row_mapping_roundtrip(graph):
    """DB rows must map to Node fields by name, not position."""
    graph.add_node(_node("x.py::a"))
    graph.conn.execute("UPDATE nodes SET centrality_score = 0.42 WHERE id = 'x.py::a'")
    graph.conn.commit()

    loaded = graph.get_node("x.py::a")
    assert loaded.centrality_score == pytest.approx(0.42)
    assert loaded.dependencies == []  # used to receive the score float


def test_edges_are_deduplicated(graph):
    """Re-indexing must not multiply identical edges."""
    graph.add_node(_node("a.py::a"))
    graph.add_node(_node("b.py::b"))
    graph.add_edge(Edge("a.py::a", "b.py::b", "imports"))
    graph.add_edge(Edge("a.py::a", "b.py::b", "imports"))

    count = graph.conn.execute(
        "SELECT COUNT(*) FROM edges WHERE source_id='a.py::a'"
    ).fetchone()[0]
    assert count == 1


def test_fts_index_stays_synchronized(graph):
    """FTS must not keep ghost entries after replace/delete."""
    graph.add_node(_node("y.py::unique_marker_name", name="unique_marker_name"))
    assert any(n.name == "unique_marker_name" for n in graph.search_nodes("unique_marker_name"))

    graph.conn.execute("DELETE FROM nodes WHERE id = 'y.py::unique_marker_name'")
    graph.conn.commit()
    hits = [n for n in graph.search_nodes("unique_marker_name") if n.id == "y.py::unique_marker_name"]
    assert hits == []


def test_delete_file_nodes_removes_subgraph(graph):
    """Deleted source files must leave no orphan nodes or dangling edges."""
    for nid in ("f1.py::a", "f1.py::b", "f2.py::c"):
        graph.add_node(_node(nid))
    graph.add_edge(Edge("f1.py::a", "f2.py::c", "imports"))
    graph.add_edge(Edge("f1.py::a", "f1.py::b", "calls"))

    graph.delete_file_nodes("f1.py")

    remaining_files = {r[0] for r in graph.conn.execute("SELECT DISTINCT file_path FROM nodes")}
    assert remaining_files == {"f2.py"}
    assert graph.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0] == 0


def test_pagerank_keeps_total_mass_with_dangling_nodes(graph):
    for i in range(4):
        graph.add_node(_node(f"d{i}.py::n{i}"))
    graph.add_edge(Edge("d0.py::n0", "d1.py::n1", "imports"))

    scores = graph.compute_pagerank()
    assert abs(sum(scores.values()) - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# Import resolution (PageRank validity)
# ---------------------------------------------------------------------------

def _entries_from(tmp_path, files):
    """Parse {relpath: content} into resolver entries (regex mode)."""
    parser = CodeParser(use_tree_sitter=False)
    entries = []
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        nodes, edges = parser.parse_file(p)
        entries.append(
            FileEntry(
                abs_path=p,
                rel_path=rel.replace("\\", "/"),
                language=detect_language(p) or "",
                symbols={n.name: n.id for n in nodes},
                raw_imports=[e.target_id for e in edges],
            )
        )
    return entries


def test_resolver_connects_python_import(temp_dir):
    entries = _entries_from(
        temp_dir,
        {
            "app.py": "from utils import helper\n",
            "utils.py": "def helper():\n    pass\n",
        },
    )
    mods, edges = ImportResolver(temp_dir).build(entries)

    mod_ids = {n.id for n in mods}
    assert "app.py::module" in mod_ids
    assert "utils.py::module" in mod_ids

    targets = [e.target_id for e in edges if e.source_id == "app.py::module"]
    assert any(t.startswith("utils.py::") for t in targets)


def test_resolver_connects_js_relative_require(temp_dir):
    entries = _entries_from(
        temp_dir,
        {
            "src/app.js": "const u = require('./util');\n",
            "src/util.js": "function go() {}\n",
        },
    )
    _, edges = ImportResolver(temp_dir).build(entries)

    targets = {e.target_id for e in edges}
    assert "src/util.js::module" in targets


def test_resolver_matches_go_import_by_stem(temp_dir):
    entries = _entries_from(
        temp_dir,
        {
            "main.go": 'package main\n\nimport "example.com/app/helpers"\n',
            "helpers.go": "package main\n",
        },
    )
    _, edges = ImportResolver(temp_dir).build(entries)

    targets = {e.target_id for e in edges}
    assert "helpers.go::module" in targets


def test_resolver_drops_unresolvable_external_imports(temp_dir):
    entries = _entries_from(temp_dir, {"a.py": "import os.path\n"})
    _, edges = ImportResolver(temp_dir).build(entries)
    assert edges == []


def test_end_to_end_pagerank_differentiates_modules(temp_dir):
    """Full indexing pipeline must yield non-uniform centrality (was uniform)."""
    (temp_dir / "core.py").write_text("def core_fn(): pass\n")
    (temp_dir / "mid.py").write_text("import core\n")
    (temp_dir / "leaf.py").write_text("import mid\n")

    from codenexus.server import CodeNexusServer

    server = CodeNexusServer(temp_dir)
    server.index_workspace(incremental=True)

    top = server.graph.get_top_central_nodes(3)
    scores = [n.centrality_score for n in top]
    assert len(scores) >= 3
    assert scores[0] > scores[-1], "centrality must differentiate modules"

    real_edges = server.graph.conn.execute(
        """
        SELECT COUNT(*) FROM edges e
        JOIN nodes s ON s.id = e.source_id
        JOIN nodes t ON t.id = e.target_id
        """
    ).fetchone()[0]
    assert real_edges >= 2
    server.graph.close()


# ---------------------------------------------------------------------------
# Parser robustness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("use_ts", [True, False])
def test_parser_cjk_source_survives(temp_dir, use_ts):
    src = "# 한글 주석: 인증 처리\ndef authenticate(user):\n    pass\n"
    p = temp_dir / "korean.py"
    p.write_text(src, encoding="utf-8")

    parser = CodeParser(use_tree_sitter=use_ts)
    nodes, _ = parser.parse_file(p)
    assert any(n.name == "authenticate" for n in nodes), f"use_tree_sitter={use_ts}"
    sig = next((n.signature for n in nodes if n.name == "authenticate"), "")
    assert "�" not in sig


@pytest.mark.parametrize("use_ts", [True, False])
def test_parser_handles_utf8_bom(temp_dir, use_ts):
    p = temp_dir / "bom.py"
    p.write_bytes(b"\xef\xbb\xbfdef bom_top():\n    pass\n")

    parser = CodeParser(use_tree_sitter=use_ts)
    nodes, _ = parser.parse_file(p)
    assert any(n.name == "bom_top" for n in nodes), f"use_tree_sitter={use_ts}"


def test_parser_java_constructor_does_not_shadow_class(temp_dir):
    p = temp_dir / "Foo.java"
    p.write_text("public class Foo {\n    public Foo() {}\n}\n", encoding="utf-8")
    parser = CodeParser(use_tree_sitter=False)
    nodes, _ = parser.parse_file(p)

    foos = [n for n in nodes if n.name == "Foo"]
    assert len(foos) == 1, "constructor must not emit a second Foo node"
    assert foos[0].node_type == "class"


def test_parser_rust_enum_captured_in_regex_mode(temp_dir):
    p = temp_dir / "lib.rs"
    p.write_text("pub enum Color {\n    Red,\n}\n", encoding="utf-8")
    parser = CodeParser(use_tree_sitter=False)
    nodes, _ = parser.parse_file(p)
    assert any(n.name == "Color" and n.node_type == "class" for n in nodes)


# ---------------------------------------------------------------------------
# MCP tool dispatch (main's architecture: SDK transport + dispatch_tool)
# ---------------------------------------------------------------------------

def test_dispatch_unknown_tool_raises_not_success(temp_dir):
    """Regression: unknown tools used to return a successful text response."""
    import asyncio

    from codenexus.server import CodeNexusServer

    srv = CodeNexusServer(temp_dir)
    with pytest.raises((ValueError, RuntimeError)):
        asyncio.run(srv.dispatch_tool("definitely_not_a_tool", {}))


def test_tools_roundtrip_on_real_index(temp_dir):
    import asyncio

    from codenexus.server import CodeNexusServer

    (temp_dir / "m.py").write_text("def searchable_thing(): pass\n")
    srv = CodeNexusServer(temp_dir)
    srv.index_workspace(incremental=True)

    status = json.loads(asyncio.run(srv.dispatch_tool("index_status", {}))[0].text)
    assert status["nodes"] >= 1

    skeleton = json.loads(
        asyncio.run(
            srv.dispatch_tool("get_skeleton", {"file_path": str(temp_dir / "m.py")})
        )[0].text
    )
    assert any("searchable_thing" in sk for sk in skeleton["skeletons"])

    capsule = asyncio.run(
        srv.dispatch_tool("get_context_capsule", {"query": "searchable_thing"})
    )
    assert "searchable_thing" in capsule[0].text


# ---------------------------------------------------------------------------
# CLI regressions
# ---------------------------------------------------------------------------

def test_cli_wizard_list_does_not_shadow_builtin(temp_dir):
    """'wizard list' once rebound builtin list and crashed other commands."""
    from click.testing import CliRunner

    from codenexus.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["wizard", "list"])
    assert result.exit_code == 0
    assert "Claude Code" in result.output


def test_cli_search_json_output(temp_dir):
    from click.testing import CliRunner

    from codenexus.cli import main
    from codenexus.server import CodeNexusServer

    (temp_dir / "q.py").write_text("def queryme(): pass\n")
    CodeNexusServer(temp_dir).index_workspace(incremental=True)

    runner = CliRunner()
    result = runner.invoke(main, ["-w", str(temp_dir), "search", "queryme", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert any(item["name"] == "queryme" for item in payload)


def test_cli_memory_decide_after_session_start(temp_dir, monkeypatch):
    from click.testing import CliRunner

    from codenexus.cli import main

    monkeypatch.chdir(temp_dir)
    runner = CliRunner()
    mem = get_memory(temp_dir / ".codenexus" / "memory.db")
    session = mem.create_session("t")

    result = runner.invoke(
        main,
        ["memory", "decide", session.id, "use sqlite cache", "-t", "architecture"],
    )
    assert result.exit_code == 0
    assert "Decision recorded" in result.output


# ---------------------------------------------------------------------------
# Session memory robustness
# ---------------------------------------------------------------------------

def test_memory_session_ids_unique_within_same_second(temp_dir):
    mem = get_memory(temp_dir / "mem.db")
    ids = {mem.create_session(f"s{i}").id for i in range(5)}
    assert len(ids) == 5


def test_memory_unknown_decision_type_degrades(temp_dir):
    mem = get_memory(temp_dir / "mem.db")
    session = mem.create_session("types")
    mem.conn.execute(
        "INSERT INTO decisions VALUES ('dx',?, 'alien_type','x','','[]',?, '[]')",
        (session.id, datetime.now().isoformat()),
    )
    mem.conn.commit()
    decisions = mem.get_decisions(session.id)
    assert decisions[0].decision_type == DecisionType.CODE_CHANGE


def test_memory_search_respects_limit(temp_dir):
    mem = get_memory(temp_dir / "mem.db")
    session = mem.create_session("bulk")
    for i in range(30):
        mem.add_decision(session.id, DecisionType.FEATURE, f"wombat item {i}")
    assert len(mem.search_decisions("wombat", limit=7)) == 7


# ---------------------------------------------------------------------------
# Licensing
# ---------------------------------------------------------------------------

from codenexus.license import LicenseManager  # noqa: E402


def test_license_has_feature_is_boolean(monkeypatch, tmp_path):
    lic = LicenseManager()
    monkeypatch.setattr(lic, "config_path", tmp_path / "license.json")
    lic._license = None  # free tier

    assert lic.has_feature("cli") is True
    assert lic.has_feature("multi_repo") is False
    assert lic.has_feature("languages") is False      # Pro-only despite non-empty free list
    assert lic.has_feature("nonexistent_feature") is False

    assert lic.activate_license("CNX-pro-acme-20991231") is True
    assert lic.has_feature("languages") is True
    assert lic.has_feature("unknown_future_feature") is False  # fail closed


def test_license_rejects_malformed_keys(monkeypatch, tmp_path):
    lic = LicenseManager()
    monkeypatch.setattr(lic, "config_path", tmp_path / "license.json")
    lic._license = None

    assert lic.activate_license("") is False
    assert lic.activate_license("NOPE") is False
    assert lic.activate_license("CNX-bogus-tier-x-20991231") is False  # unknown tier
    assert lic.activate_license("CNX-pro-acme-20200101") is False      # expired


def test_license_gates_workspace_repos(temp_dir, monkeypatch):
    from codenexus.workspace import MultiRepoWorkspace

    lic = LicenseManager()
    monkeypatch.setattr(lic, "config_path", temp_dir / "license.json")
    lic._license = None
    monkeypatch.setattr("codenexus.workspace.get_license", lambda: lic)

    ws = MultiRepoWorkspace(temp_dir)
    assert ws.add_repo("one", temp_dir) is True
    assert ws.add_repo("two", temp_dir) is False        # free tier cap

    assert lic.activate_license("CNX-pro-acme-20991231") is True
    assert ws.add_repo("two", temp_dir) is True         # pro lifts cap


# ---------------------------------------------------------------------------
# Wizard config safety
# ---------------------------------------------------------------------------

def test_wizard_never_overwrites_corrupt_config(tmp_path):
    from codenexus.wizard import AgentWizard

    cfg = tmp_path / "agent.json"
    cfg.write_text("{corrupt!!", encoding="utf-8")

    wiz = AgentWizard()
    info = SimpleNamespace(config_file=str(cfg), name="TestAgent")
    ok = wiz._apply_mcp_config(info, {"mcpServers": {"codenexus": {"command": "codenexus"}}})

    assert ok is False
    assert cfg.read_text(encoding="utf-8") == "{corrupt!!"  # untouched


def test_wizard_merge_creates_backup_and_preserves_data(tmp_path):
    from codenexus.wizard import AgentWizard

    cfg = tmp_path / "agent.json"
    cfg.write_text(json.dumps({"projects": {"p1": {"history": [1]}}}), encoding="utf-8")

    wiz = AgentWizard()
    info = SimpleNamespace(config_file=str(cfg), name="TestAgent")
    ok = wiz._apply_mcp_config(info, {"mcpServers": {"codenexus": {"command": "codenexus"}}})

    assert ok is True
    merged = json.loads(cfg.read_text(encoding="utf-8"))
    assert merged["projects"]["p1"]["history"] == [1]
    assert "codenexus" in merged["mcpServers"]
    assert (tmp_path / "agent.json.codenexus-backup").exists()
