"""Core graph engine for CodeNexus."""

import sqlite3
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict
import math

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
    dependencies: list[str] = None
    centrality_score: float = 0.0  # PageRank 점수
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []

@dataclass
class Edge:
    source_id: str
    target_id: str
    edge_type: str  # calls, imports, defines, etc.

class DependencyGraph:
    """SQLite-based dependency graph with PageRank centrality."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_schema()
    
    def _init_schema(self):
        self.conn.executescript("""
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
            
            CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file_path);
            CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
            CREATE INDEX IF NOT EXISTS idx_nodes_centrality ON nodes(centrality_score DESC);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
        """)
        
        # Create FTS5 table separately (may not be available in all SQLite builds)
        try:
            self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
                    name, content, signature,
                    content=nodes,
                    content_rowid=rowid
                )
            """)
        except Exception:
            # FTS5 not available, will use fallback search
            pass
        
        self.conn.commit()
    
    def add_node(self, node: Node):
        self.conn.execute("""
            INSERT OR REPLACE INTO nodes (id, file_path, name, node_type, 
                                          start_line, end_line, content, signature,
                                          centrality_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (node.id, node.file_path, node.name, node.node_type,
              node.start_line, node.end_line, node.content, node.signature,
              node.centrality_score))
        
        # Update FTS index if available
        try:
            self.conn.execute("""
                INSERT OR REPLACE INTO nodes_fts (rowid, name, content, signature)
                VALUES (
                    (SELECT rowid FROM nodes WHERE id = ?),
                    ?, ?, ?
                )
            """, (node.id, node.name, node.content, node.signature))
        except Exception:
            pass
        
        self.conn.commit()
    
    def add_edge(self, edge: Edge):
        self.conn.execute("""
            INSERT INTO edges (source_id, target_id, edge_type)
            VALUES (?, ?, ?)
        """, (edge.source_id, edge.target_id, edge.edge_type))
        self.conn.commit()
    
    def get_node(self, node_id: str) -> Optional[Node]:
        row = self.conn.execute(
            "SELECT * FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if row:
            return Node(*row[:9])  # centrality_score 포함
        return None
    
    def get_dependents(self, node_id: str) -> list[Node]:
        rows = self.conn.execute("""
            SELECT n.* FROM nodes n
            JOIN edges e ON n.id = e.source_id
            WHERE e.target_id = ?
        """, (node_id,)).fetchall()
        return [Node(*row[:9]) for row in rows]
    
    def get_dependencies(self, node_id: str) -> list[Node]:
        rows = self.conn.execute("""
            SELECT n.* FROM nodes n
            JOIN edges e ON n.id = e.target_id
            WHERE e.source_id = ?
        """, (node_id,)).fetchall()
        return [Node(*row[:9]) for row in rows]
    
    def search_nodes(self, query: str, limit: int = 10, 
                     use_centrality: bool = True) -> list[Node]:
        """Search nodes with optional centrality ranking."""
        # Try FTS5 search first
        try:
            if use_centrality:
                rows = self.conn.execute("""
                    SELECT n.* FROM nodes n
                    JOIN nodes_fts fts ON n.rowid = fts.rowid
                    WHERE nodes_fts MATCH ?
                    ORDER BY n.centrality_score DESC
                    LIMIT ?
                """, (query, limit)).fetchall()
            else:
                rows = self.conn.execute("""
                    SELECT n.* FROM nodes n
                    JOIN nodes_fts fts ON n.rowid = fts.rowid
                    WHERE nodes_fts MATCH ?
                    LIMIT ?
                """, (query, limit)).fetchall()
            
            if rows:
                return [Node(*row[:9]) for row in rows]
        except Exception:
            pass
        
        # Fallback to LIKE search
        if use_centrality:
            rows = self.conn.execute("""
                SELECT * FROM nodes 
                WHERE name LIKE ? OR content LIKE ? OR signature LIKE ?
                ORDER BY centrality_score DESC
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", limit)).fetchall()
        else:
            rows = self.conn.execute("""
                SELECT * FROM nodes 
                WHERE name LIKE ? OR content LIKE ? OR signature LIKE ?
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", limit)).fetchall()
        
        return [Node(*row[:9]) for row in rows]
    
    def get_skeleton(self, node_id: str) -> str:
        node = self.get_node(node_id)
        if not node:
            return ""
        return node.signature
    
    def compute_pagerank(self, damping: float = 0.85, 
                         iterations: int = 20,
                         tolerance: float = 1e-6) -> dict[str, float]:
        """
        Compute PageRank centrality for all nodes.
        
        Args:
            damping: Damping factor (probability of following a link)
            iterations: Maximum number of iterations
            tolerance: Convergence threshold
        
        Returns:
            Dictionary mapping node_id to PageRank score
        """
        # Get all nodes and edges
        nodes = self.conn.execute("SELECT id FROM nodes").fetchall()
        node_ids = [row[0] for row in nodes]
        n = len(node_ids)
        
        if n == 0:
            return {}
        
        # Build adjacency lists
        outgoing = defaultdict(list)  # node -> nodes it points to
        incoming = defaultdict(list)  # node -> nodes pointing to it
        
        edges = self.conn.execute("SELECT source_id, target_id FROM edges").fetchall()
        for source, target in edges:
            if source in node_ids and target in node_ids:
                outgoing[source].append(target)
                incoming[target].append(source)
        
        # Initialize PageRank scores
        pr = {node_id: 1.0 / n for node_id in node_ids}
        
        # Iterate
        for iteration in range(iterations):
            new_pr = {}
            max_diff = 0
            
            for node_id in node_ids:
                # Sum of incoming contributions
                rank_sum = 0
                for incoming_node in incoming[node_id]:
                    out_degree = len(outgoing[incoming_node])
                    if out_degree > 0:
                        rank_sum += pr[incoming_node] / out_degree
                
                # PageRank formula
                new_score = (1 - damping) / n + damping * rank_sum
                new_pr[node_id] = new_score
                
                # Track convergence
                max_diff = max(max_diff, abs(new_score - pr[node_id]))
            
            pr = new_pr
            
            # Check convergence
            if max_diff < tolerance:
                print(f"PageRank converged after {iteration + 1} iterations")
                break
        
        # Store scores in database
        for node_id, score in pr.items():
            self.conn.execute("""
                UPDATE nodes SET centrality_score = ? WHERE id = ?
            """, (score, node_id))
            
            # Update cache
            self.conn.execute("""
                INSERT OR REPLACE INTO centrality_cache (node_id, score)
                VALUES (?, ?)
            """, (node_id, score))
        
        self.conn.commit()
        return pr
    
    def get_centrality_scores(self) -> dict[str, float]:
        """Get cached centrality scores."""
        rows = self.conn.execute(
            "SELECT node_id, score FROM centrality_cache"
        ).fetchall()
        return {row[0]: row[1] for row in rows}
    
    def get_top_central_nodes(self, limit: int = 10) -> list[Node]:
        """Get nodes with highest centrality scores."""
        rows = self.conn.execute("""
            SELECT * FROM nodes 
            ORDER BY centrality_score DESC 
            LIMIT ?
        """, (limit,)).fetchall()
        return [Node(*row[:9]) for row in rows]
    
    def get_impact_graph(self, node_id: str, depth: int = 2) -> dict:
        """
        Get impact graph for a node (what would be affected by changes).
        
        Args:
            node_id: Starting node
            depth: How many levels of dependencies to traverse
        
        Returns:
            Dictionary with direct and indirect dependents
        """
        impact = {
            "direct": [],
            "indirect": [],
            "total_tokens": 0
        }
        
        visited = set()
        queue = [(node_id, 0)]
        
        while queue:
            current_id, current_depth = queue.pop(0)
            
            if current_id in visited or current_depth > depth:
                continue
            
            visited.add(current_id)
            
            # Find nodes that DEPEND ON this node (callers)
            # edge: caller -> current_id (source -> target)
            dependents = self.conn.execute("""
                SELECT n.* FROM nodes n
                JOIN edges e ON n.id = e.source_id
                WHERE e.target_id = ?
            """, (current_id,)).fetchall()
            
            for row in dependents:
                dep = Node(*row[:9])
                if current_depth == 0:
                    impact["direct"].append({
                        "id": dep.id,
                        "name": dep.name,
                        "file": dep.file_path
                    })
                else:
                    impact["indirect"].append({
                        "id": dep.id,
                        "name": dep.name,
                        "file": dep.file_path,
                        "depth": current_depth
                    })
                
                if current_depth < depth:
                    queue.append((dep.id, current_depth + 1))
        
        impact["total"] = len(impact["direct"]) + len(impact["indirect"])
        return impact
    
    def clear(self):
        self.conn.executescript("""
            DELETE FROM edges;
            DELETE FROM nodes;
            DELETE FROM centrality_cache;
        """)
        try:
            self.conn.execute("DELETE FROM nodes_fts")
        except:
            pass
        self.conn.commit()
    
    def close(self):
        self.conn.close()
