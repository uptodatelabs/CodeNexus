"""Read-only federation over one or more member indexes.

``FederatedGraph`` exposes the same read API the MCP tools consume as a
single ``DependencyGraph``, fanning queries out to every member repo and
merging results by centrality. Writes stay per-repo (see
``MultiRepoWorkspace.index_repo``); this class never mutates member stores.

This is what makes *one agent registration serve many indexes*: point
``codenexus serve -w`` at a directory containing
``.codenexus/workspace.json`` and every registered repo becomes queryable
through the same tools.
"""

import logging
from pathlib import Path

from .graph import DependencyGraph, Node

logger = logging.getLogger(__name__)


class FederatedGraph:
    """Query facade over multiple member ``DependencyGraph`` instances."""

    def __init__(self, members: list[tuple[str, DependencyGraph]]):
        # members: [(repo_alias, graph)] — alias is '' for a lone unnamed store.
        if not members:
            raise ValueError("FederatedGraph needs at least one member graph")
        self.members = members

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def search_nodes(
        self, query: str, limit: int = 10, use_centrality: bool = True
    ) -> list[Node]:
        """Search all member repos; merge ranked by centrality."""
        merged: list[Node] = []
        seen: set[tuple[str, str]] = set()  # (alias, node_id)
        for alias, graph in self.members:
            for node in graph.search_nodes(query, limit=limit, use_centrality=use_centrality):
                key = (alias, node.id)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(node)
        merged.sort(key=lambda n: n.centrality_score, reverse=True)
        return merged[:limit]

    def get_file_nodes(self, file_path: str) -> list[Node]:
        """Return nodes for an aliased path (``alpha/src/app.py``).

        Member paths are alias-prefixed by the workspace indexer, so the
        first member holding this exact path owns it exclusively.
        """
        for _, graph in self.members:
            nodes = graph.get_file_nodes(file_path)
            if nodes:
                return nodes
        return []

    def get_node(self, node_id: str) -> Node | None:
        for _, graph in self.members:
            node = graph.get_node(node_id)
            if node is not None:
                return node
        return None

    def get_impact_graph(self, node_id: str, depth: int = 2) -> dict:
        """Impact analysis runs inside the single repo owning the node."""
        for alias, graph in self.members:
            probe = graph.get_node(node_id)
            if probe is None:
                # Node ids may be bare names shared across repos; fall back
                # to any repo that has edges touching this id.
                hit = graph.conn.execute(
                    "SELECT 1 FROM edges WHERE source_id = ? OR target_id = ? LIMIT 1",
                    (node_id, node_id),
                ).fetchone()
                if hit is None:
                    continue
            logger.debug("impact(%s) resolved in repo %r", node_id, alias)
            return graph.get_impact_graph(node_id, depth=depth)
        return {"direct": [], "indirect": [], "total": 0}

    def get_top_central_nodes(self, limit: int = 10) -> list[Node]:
        merged: list[Node] = []
        for _, graph in self.members:
            merged.extend(graph.get_top_central_nodes(limit))
        merged.sort(key=lambda n: n.centrality_score, reverse=True)
        return merged[:limit]

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def counts(self) -> dict:
        """Aggregate index statistics plus a per-repo breakdown."""
        total_nodes = total_edges = total_files = 0
        repos = []
        for alias, graph in self.members:
            nodes = graph.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edges = graph.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            files = graph.conn.execute(
                "SELECT COUNT(DISTINCT file_path) FROM nodes"
            ).fetchone()[0]
            repos.append({"alias": alias, "nodes": nodes, "edges": edges, "files": files})
            total_nodes += nodes
            total_edges += edges
            total_files += files
        return {
            "nodes": total_nodes,
            "edges": total_edges,
            "files": total_files,
            "mode": "multi-repo",
            "repos": repos,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    @classmethod
    def from_workspace(cls, workspace_path: Path) -> "FederatedGraph | None":
        """Build from ``<ws>/.codenexus/workspace.json`` when present.

        Only repos with an existing database participate; registering a repo
        without indexing it simply leaves it out until indexed.
        """
        from .workspace import MultiRepoWorkspace

        ws = MultiRepoWorkspace(Path(workspace_path))
        if not getattr(ws, "_config_load_ok", True) or not ws.config or not ws.config.repos:
            return None
        members: list[tuple[str, DependencyGraph]] = []
        for repo in ws.config.repos:
            graph = ws._open_existing_graph(repo.alias)
            if graph is not None:
                members.append((repo.alias, graph))
        if not members:
            return None
        logger.info("Federating %d member indexes", len(members))
        return cls(members)

    def close(self):
        for _, graph in self.members:
            graph.close()
