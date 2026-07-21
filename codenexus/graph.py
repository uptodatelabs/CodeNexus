"""Core graph engine for vexp-lite."""

import sqlite3
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

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
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []

@dataclass
class Edge:
    source_id: str
    target_id: str
    edge_type: str  # calls, imports, defines, etc.

class DependencyGraph:
    """SQLite-based dependency graph."""
    
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
            
            CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file_path);
            CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
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
                                          start_line, end_line, content, signature)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (node.id, node.file_path, node.name, node.node_type,
              node.start_line, node.end_line, node.content, node.signature))
        
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
            return Node(*row[:8])
        return None
    
    def get_dependents(self, node_id: str) -> list[Node]:
        rows = self.conn.execute("""
            SELECT n.* FROM nodes n
            JOIN edges e ON n.id = e.source_id
            WHERE e.target_id = ?
        """, (node_id,)).fetchall()
        return [Node(*row[:8]) for row in rows]
    
    def search_nodes(self, query: str, limit: int = 10) -> list[Node]:
        # Try FTS5 search first
        try:
            rows = self.conn.execute("""
                SELECT n.* FROM nodes n
                JOIN nodes_fts fts ON n.rowid = fts.rowid
                WHERE nodes_fts MATCH ?
                LIMIT ?
            """, (query, limit)).fetchall()
            if rows:
                return [Node(*row[:8]) for row in rows]
        except Exception:
            pass
        
        # Fallback to LIKE search
        rows = self.conn.execute("""
            SELECT * FROM nodes 
            WHERE name LIKE ? OR content LIKE ? OR signature LIKE ?
            LIMIT ?
        """, (f"%{query}%", f"%{query}%", f"%{query}%", limit)).fetchall()
        return [Node(*row[:8]) for row in rows]
    
    def get_skeleton(self, node_id: str) -> str:
        node = self.get_node(node_id)
        if not node:
            return ""
        return node.signature
    
    def clear(self):
        self.conn.executescript("""
            DELETE FROM edges;
            DELETE FROM nodes;
            DELETE FROM nodes_fts;
        """)
        self.conn.commit()
    
    def close(self):
        self.conn.close()
