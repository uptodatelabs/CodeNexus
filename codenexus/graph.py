"""Core graph engine for CodeNexus."""

import logging
import sqlite3
import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Bump when schema/migration logic changes to trigger a one-time migration.
SCHEMA_VERSION = "2"

# Explicit column list — never use SELECT * so row order is guaranteed to
# match _node_from_row regardless of future ALTER TABLE additions.
_NODE_COLS = (
    "id",
    "file_path",
    "name",
    "node_type",
    "start_line",
    "end_line",
    "content",
    "signature",
    "centrality_score",
)


def _node_select(alias: str = "nodes") -> str:
    """Comma-separated column list qualified by table alias (JOIN-safe)."""
    return ", ".join(f"{alias}.{col}" for col in _NODE_COLS)


@dataclass
class Node:
    id: str
    file_path: str
    name: str
    node_type: str  # function, class, method, import, etc.
    start_line: int
    end_line: int
    content: str
    signature: str
    dependencies: list[str] | None = None
    centrality_score: float = 0.0

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []


@dataclass
class Edge:
    source_id: str
    target_id: str
    edge_type: str  # calls, imports, defines, etc.


class DependencyGraph:
    """SQLite-based dependency graph with PageRank centrality.

    Thread-safe: all public methods serialize access to the underlying
    connection through an internal lock, so a single instance may be shared
    across threads.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._fts_available = False
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema / migration
    # ------------------------------------------------------------------
    def _init_schema(self):
        with self._lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    node_type TEXT NOT NULL,
                    start_line INTEGER,
                    end_line INTEGER,
                    content TEXT,
                    signature TEXT,
                    centrality_score REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    FOREIGN KEY (source_id) REFERENCES nodes(id),
                    FOREIGN KEY (target_id) REFERENCES nodes(id)
                );

                CREATE TABLE IF NOT EXISTS centrality_cache (
                    node_id TEXT PRIMARY KEY,
                    score REAL,
                    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file_path);
                CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
                CREATE INDEX IF NOT EXISTS idx_nodes_centrality ON nodes(centrality_score DESC);
                CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
                """
            )

            try:
                self.conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
                        name, content, signature,
                        content=nodes,
                        content_rowid=rowid
                    )
                    """
                )
                # External-content FTS5 requires triggers to stay in sync.
                self.conn.executescript(
                    """
                    CREATE TRIGGER IF NOT EXISTS nodes_fts_ad AFTER INSERT ON nodes BEGIN
                        INSERT INTO nodes_fts(rowid, name, content, signature)
                        VALUES (new.rowid, new.name, new.content, new.signature);
                    END;

                    CREATE TRIGGER IF NOT EXISTS nodes_fts_bd BEFORE DELETE ON nodes BEGIN
                        INSERT INTO nodes_fts(nodes_fts, rowid, name, content, signature)
                        VALUES ('delete', old.rowid, old.name, old.content, old.signature);
                    END;

                    CREATE TRIGGER IF NOT EXISTS nodes_fts_au AFTER UPDATE ON nodes BEGIN
                        INSERT INTO nodes_fts(nodes_fts, rowid, name, content, signature)
                        VALUES ('delete', old.rowid, old.name, old.content, old.signature);
                        INSERT INTO nodes_fts(rowid, name, content, signature)
                        VALUES (new.rowid, new.name, new.content, new.signature);
                    END;
                    """
                )
                self._fts_available = True
            except sqlite3.Error:
                # FTS5 not available in this SQLite build; LIKE fallback is used.
                logger.debug("FTS5 unavailable; falling back to LIKE search")

            self._migrate_if_needed()
            self.conn.commit()

    def _migrate_if_needed(self):
        """One-time migrations guarded by schema_meta.schema_version."""
        row = self.conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is not None and row[0] == SCHEMA_VERSION:
            return

        # v1 -> v2: collapse duplicate edges accumulated by pre-unique indexing,
        # enforce uniqueness going forward, and rebuild the (previously
        # unsynchronized) FTS index from scratch.
        self.conn.execute(
            """
            DELETE FROM edges WHERE id NOT IN (
                SELECT MIN(id) FROM edges GROUP BY source_id, target_id, edge_type
            )
            """
        )
        self.conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_edges_unique "
            "ON edges(source_id, target_id, edge_type)"
        )
        if self._fts_available:
            try:
                self.conn.execute("INSERT INTO nodes_fts(nodes_fts) VALUES ('rebuild')")
            except sqlite3.Error:
                logger.warning("FTS5 rebuild failed; search falls back to LIKE", exc_info=True)

        self.conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        logger.info("Index schema migrated to version %s", SCHEMA_VERSION)

    def _node_from_row(self, row: tuple) -> Node:
        """Build a Node from a row selected with _NODE_COLUMNS.

        Positional unpacking is deliberately avoided: column order and
        dataclass field order diverged silently once before (dependencies vs
        centrality_score).
        """
        return Node(
            id=row[0],
            file_path=row[1],
            name=row[2],
            node_type=row[3],
            start_line=row[4] if row[4] is not None else 0,
            end_line=row[5] if row[5] is not None else 0,
            content=row[6] or "",
            signature=row[7] or "",
            centrality_score=row[8] if row[8] is not None else 0.0,
        )

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def add_node(self, node: Node):
        with self._lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO nodes (id, file_path, name, node_type,
                                              start_line, end_line, content, signature,
                                              centrality_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node.id,
                    node.file_path,
                    node.name,
                    node.node_type,
                    node.start_line,
                    node.end_line,
                    node.content,
                    node.signature,
                    node.centrality_score,
                ),
            )
            self.conn.commit()

    def add_nodes(self, nodes: list[Node]):
        """Insert many nodes in a single transaction."""
        if not nodes:
            return
        with self._lock:
            self.conn.executemany(
                """
                INSERT OR REPLACE INTO nodes (id, file_path, name, node_type,
                                              start_line, end_line, content, signature,
                                              centrality_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        n.id,
                        n.file_path,
                        n.name,
                        n.node_type,
                        n.start_line,
                        n.end_line,
                        n.content,
                        n.signature,
                        n.centrality_score,
                    )
                    for n in nodes
                ],
            )
            self.conn.commit()

    def add_edge(self, edge: Edge):
        with self._lock:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO edges (source_id, target_id, edge_type)
                VALUES (?, ?, ?)
                """,
                (edge.source_id, edge.target_id, edge.edge_type),
            )
            self.conn.commit()

    def add_edges(self, edges: list[Edge]):
        """Insert many edges in a single transaction; duplicates are ignored."""
        if not edges:
            return
        with self._lock:
            self.conn.executemany(
                """
                INSERT OR IGNORE INTO edges (source_id, target_id, edge_type)
                VALUES (?, ?, ?)
                """,
                [(e.source_id, e.target_id, e.edge_type) for e in edges],
            )
            self.conn.commit()

    def delete_file_nodes(self, file_path: str):
        """Remove all nodes belonging to a file plus their edges and caches.

        Used to purge stale entries when a source file is deleted or renamed.
        FTS sync is handled by triggers.
        """
        with self._lock:
            self.conn.execute(
                """
                DELETE FROM edges WHERE source_id IN
                    (SELECT id FROM nodes WHERE file_path = ?)
                   OR target_id IN
                    (SELECT id FROM nodes WHERE file_path = ?)
                """,
                (file_path, file_path),
            )
            self.conn.execute(
                """
                DELETE FROM centrality_cache WHERE node_id IN
                    (SELECT id FROM nodes WHERE file_path = ?)
                """,
                (file_path,),
            )
            self.conn.execute("DELETE FROM nodes WHERE file_path = ?", (file_path,))
            self.conn.commit()

    def clear(self):
        with self._lock:
            self.conn.executescript(
                """
                DELETE FROM edges;
                DELETE FROM nodes;
                DELETE FROM centrality_cache;
                """
            )
            self.conn.commit()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def get_node(self, node_id: str) -> Node | None:
        with self._lock:
            row = self.conn.execute(
                f"SELECT {_node_select()} FROM nodes WHERE id = ?", (node_id,)
            ).fetchone()
        if row:
            return self._node_from_row(row)
        return None

    def get_dependents(self, node_id: str) -> list[Node]:
        with self._lock:
            rows = self.conn.execute(
                f"""
                SELECT {_node_select('n')} FROM nodes n
                JOIN edges e ON n.id = e.source_id
                WHERE e.target_id = ?
                """,
                (node_id,),
            ).fetchall()
        return [self._node_from_row(row) for row in rows]

    def get_dependencies(self, node_id: str) -> list[Node]:
        with self._lock:
            rows = self.conn.execute(
                f"""
                SELECT {_node_select('n')} FROM nodes n
                JOIN edges e ON n.id = e.target_id
                WHERE e.source_id = ?
                """,
                (node_id,),
            ).fetchall()
        return [self._node_from_row(row) for row in rows]

    @staticmethod
    def _escape_like(query: str) -> str:
        """Escape LIKE wildcards so user queries match literally."""
        return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def search_nodes(
        self, query: str, limit: int = 10, use_centrality: bool = True
    ) -> list[Node]:
        """Search nodes with optional centrality ranking."""
        order_by = "ORDER BY n.centrality_score DESC" if use_centrality else ""
        if self._fts_available:
            with self._lock:
                try:
                    rows = self.conn.execute(
                        f"""
                        SELECT {_node_select('n')} FROM nodes n
                        JOIN nodes_fts fts ON n.rowid = fts.rowid
                        WHERE nodes_fts MATCH ?
                        {order_by}
                        LIMIT ?
                        """,
                        (query, limit),
                    ).fetchall()
                    return [self._node_from_row(row) for row in rows]
                except sqlite3.Error:
                    # Malformed FTS query syntax (special chars etc.) — fall through.
                    logger.debug("FTS query failed for %r; using LIKE fallback", query)

        escaped = self._escape_like(query)
        pattern = f"%{escaped}%"
        order_clause = "ORDER BY centrality_score DESC" if use_centrality else ""
        with self._lock:
            rows = self.conn.execute(
                f"""
                SELECT {_node_select()} FROM nodes
                WHERE name LIKE ? ESCAPE '\\'
                   OR content LIKE ? ESCAPE '\\'
                   OR signature LIKE ? ESCAPE '\\'
                {order_clause}
                LIMIT ?
                """,
                (pattern, pattern, pattern, limit),
            ).fetchall()
        return [self._node_from_row(row) for row in rows]

    def get_file_nodes(self, file_path: str) -> list[Node]:
        """Return every node recorded for a file, ordered by position."""
        with self._lock:
            rows = self.conn.execute(
                f"""
                SELECT {_node_select()} FROM nodes
                WHERE file_path = ?
                ORDER BY start_line ASC
                """,
                (file_path,),
            ).fetchall()
        return [self._node_from_row(row) for row in rows]

    def get_skeleton(self, node_id: str) -> str:
        node = self.get_node(node_id)
        if not node:
            return ""
        return node.signature

    # ------------------------------------------------------------------
    # Centrality
    # ------------------------------------------------------------------
    def compute_pagerank(
        self, damping: float = 0.85, iterations: int = 20, tolerance: float = 1e-6
    ) -> dict[str, float]:
        """
        Compute PageRank centrality for all nodes.

        Args:
            damping: Damping factor (probability of following a link)
            iterations: Maximum number of iterations
            tolerance: Convergence threshold

        Returns:
            Dictionary mapping node_id to PageRank score
        """
        with self._lock:
            node_ids = [row[0] for row in self.conn.execute("SELECT id FROM nodes")]
            n = len(node_ids)

            if n == 0:
                return {}

            # Build adjacency lists. Membership tests use a set: this loop ran
            # O(E*N) against a list before.
            id_set = set(node_ids)
            outgoing: dict[str, list[str]] = defaultdict(list)
            incoming: dict[str, list[str]] = defaultdict(list)
            edges = self.conn.execute(
                "SELECT DISTINCT source_id, target_id FROM edges"
            ).fetchall()
            for source, target in edges:
                if source in id_set and target in id_set:
                    if target not in outgoing[source]:
                        outgoing[source].append(target)
                        incoming[target].append(source)

            # Nodes with no outbound links would leak rank mass every sweep;
            # redistribute it uniformly so total rank stays at 1.0.
            dangling = [node_id for node_id in node_ids if not outgoing[node_id]]

            # Initialize PageRank scores
            pr = {node_id: 1.0 / n for node_id in node_ids}

            # Power iteration
            for iteration in range(iterations):
                dangling_mass = sum(pr[node_id] for node_id in dangling)
                base = (1 - damping) / n + damping * dangling_mass / n

                new_pr = {}
                max_diff = 0.0
                for node_id in node_ids:
                    rank_sum = 0.0
                    for incoming_node in incoming[node_id]:
                        out_degree = len(outgoing[incoming_node])
                        if out_degree > 0:
                            rank_sum += pr[incoming_node] / out_degree

                    score = base + damping * rank_sum
                    new_pr[node_id] = score
                    max_diff = max(max_diff, abs(score - pr[node_id]))

                pr = new_pr
                if max_diff < tolerance:
                    logger.debug("PageRank converged after %d iterations", iteration + 1)
                    break

            # Store scores in database
            self.conn.executemany(
                "UPDATE nodes SET centrality_score = ? WHERE id = ?",
                [(score, node_id) for node_id, score in pr.items()],
            )
            self.conn.executemany(
                """
                INSERT OR REPLACE INTO centrality_cache (node_id, score)
                VALUES (?, ?)
                """,
                [(node_id, score) for node_id, score in pr.items()],
            )
            self.conn.commit()

        return pr

    def get_centrality_scores(self) -> dict[str, float]:
        """Get cached centrality scores."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT node_id, score FROM centrality_cache"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def get_top_central_nodes(self, limit: int = 10) -> list[Node]:
        """Get nodes with highest centrality scores."""
        with self._lock:
            rows = self.conn.execute(
                f"""
                SELECT {_node_select()} FROM nodes
                ORDER BY centrality_score DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._node_from_row(row) for row in rows]

    def get_impact_graph(self, node_id: str, depth: int = 2) -> dict:
        """
        Get impact graph for a node (what would be affected by changes).

        Args:
            node_id: Starting node
            depth: How many levels of dependencies to traverse

        Returns:
            Dictionary with direct and indirect dependents
        """
        impact: dict = {"direct": [], "indirect": []}

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])

        while queue:
            current_id, current_depth = queue.popleft()

            if current_id in visited or current_depth > depth:
                continue
            visited.add(current_id)

            # Find nodes that DEPEND ON this node (callers)
            with self._lock:
                dependents = self.conn.execute(
                    f"""
                    SELECT {_node_select('n')} FROM nodes n
                    JOIN edges e ON n.id = e.source_id
                    WHERE e.target_id = ?
                    """,
                    (current_id,),
                ).fetchall()

            for row in dependents:
                dep = self._node_from_row(row)
                entry = {"id": dep.id, "name": dep.name, "file": dep.file_path}
                if current_depth == 0:
                    impact["direct"].append(entry)
                else:
                    impact["indirect"].append({**entry, "depth": current_depth})

                if current_depth < depth:
                    queue.append((dep.id, current_depth + 1))

        impact["total"] = len(impact["direct"]) + len(impact["indirect"])
        return impact

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def close(self):
        with self._lock:
            self.conn.close()

    def __enter__(self) -> "DependencyGraph":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
