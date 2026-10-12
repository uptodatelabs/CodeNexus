"""Regression tests: hardcoded MCP server version (D1) and dead ``self.tier``
artifact in the indexing path (D2).

D1: ``codenexus/server.py`` and ``codenexus/mcp_server.py`` built the MCP
``Server`` with a hardcoded ``version="1.1.40"`` while the single source of
truth (``codenexus/_version.py``) is the real package version. The advertised
version must always come from ``_version.__version__``.

D2: ``index_workspace`` still contained an unreachable ``truncated`` branch
that referenced ``self.tier.value`` — an attribute that no longer exists.
The dead truncation code is removed; the observable guarantee is that full
indexing keeps every node.
"""

import inspect

import codenexus.server as server_mod
from codenexus._version import __version__


def test_engine_sdk_server_version_matches_single_source(tmp_path):
    """The engine's embedded MCP SDK server must advertise the real version."""
    from codenexus.server import CodeNexusServer

    engine = CodeNexusServer(tmp_path)
    assert engine.server.name == "codenexus"
    assert engine.server.version == __version__, (
        f"MCP server advertises {engine.server.version!r}, "
        f"expected {__version__!r}"
    )


def test_transport_server_version_matches_single_source(tmp_path):
    """The stdio transport server must advertise the real version too."""
    from codenexus.mcp_server import create_server

    sdk = create_server(str(tmp_path))
    assert sdk.name == "codenexus"
    assert sdk.version == __version__, (
        f"transport advertises {sdk.version!r}, expected {__version__!r}"
    )


def test_indexing_source_has_no_tier_artifact(tmp_path):
    """The indexing path must not reference the removed ``self.tier``."""
    src = inspect.getsource(server_mod)
    assert "self.tier" not in src, "dead self.tier reference still present"


def test_full_indexing_keeps_every_node(tmp_path):
    """Behavior guard: without a tier/node cap, all parsed symbols are stored."""
    from codenexus.server import CodeNexusServer

    (tmp_path / "a.py").write_text("def alpha():\n    pass\n\nclass Beta:\n    pass\n")
    (tmp_path / "b.py").write_text("import a\n\ndef gamma():\n    return a.alpha()\n")

    engine = CodeNexusServer(tmp_path)
    count = engine.index_workspace(incremental=True)
    assert count == 2

    names = {row[0] for row in engine.graph.conn.execute("SELECT name FROM nodes")}
    assert {"alpha", "Beta", "gamma"} <= names
    edges = engine.graph.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    assert edges >= 1  # a.py::module -> import resolved to something real
    engine.graph.close()
