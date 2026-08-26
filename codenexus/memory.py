"""Session memory and decision tracking for CodeNexus."""

import json
import logging
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class DecisionType(Enum):
    """Types of decisions to track."""

    CODE_CHANGE = "code_change"
    ARCHITECTURE = "architecture"
    BUG_FIX = "bug_fix"
    REFACTOR = "refactor"
    FEATURE = "feature"
    CONFIG = "config"


def _coerce_decision_type(value: str) -> DecisionType:
    """Map a stored decision type to the enum, tolerating unknown values.

    Older or foreign rows must not crash reads; unknown values degrade to
    CODE_CHANGE with a warning.
    """
    try:
        return DecisionType(value)
    except ValueError:
        logger.warning("Unknown decision type %r stored in DB; reading as code_change", value)
        return DecisionType.CODE_CHANGE


@dataclass
class Session:
    """Session information."""

    id: str
    name: str
    start_time: datetime
    end_time: datetime | None = None
    summary: str = ""
    files_changed: list[str] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)


@dataclass
class Decision:
    """Decision record."""

    id: str
    session_id: str
    decision_type: DecisionType
    description: str
    rationale: str
    files_affected: list[str] | None = None
    timestamp: datetime | None = None
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.files_affected is None:
            self.files_affected = []
        if self.timestamp is None:
            self.timestamp = datetime.now()


class SessionMemory:
    """Manages session memory and decision tracking.

    Thread-safe: all public methods serialize access through an internal lock,
    mirroring DependencyGraph.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema."""
        with self._lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    summary TEXT,
                    files_changed TEXT DEFAULT '[]'
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    decision_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    rationale TEXT,
                    files_affected TEXT DEFAULT '[]',
                    timestamp TIMESTAMP NOT NULL,
                    tags TEXT DEFAULT '[]',
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    context TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS file_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    file_path TEXT NOT NULL,
                    change_type TEXT NOT NULL,
                    line_count INTEGER DEFAULT 0,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_decisions_session ON decisions(session_id);
                CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id);
                CREATE INDEX IF NOT EXISTS idx_file_changes_session ON file_changes(session_id);
            """)
            self.conn.commit()

    @staticmethod
    def _new_session_id() -> str:
        # Seconds-resolution ids collided when two sessions started in the
        # same second (unhandled IntegrityError); a random suffix fixes that.
        return f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    def create_session(self, name: str) -> Session:
        """Create a new session."""
        session_id = self._new_session_id()
        start_time = datetime.now()

        with self._lock:
            self.conn.execute(
                """
                INSERT INTO sessions (id, name, start_time)
                VALUES (?, ?, ?)
            """,
                (session_id, name, start_time.isoformat()),
            )
            self.conn.commit()

        return Session(id=session_id, name=name, start_time=start_time)

    def end_session(self, session_id: str, summary: str = ""):
        """End a session."""
        end_time = datetime.now()

        with self._lock:
            self.conn.execute(
                """
                UPDATE sessions SET end_time = ?, summary = ?
                WHERE id = ?
            """,
                (end_time.isoformat(), summary, session_id),
            )
            self.conn.commit()

    @staticmethod
    def _session_from_row(row) -> Session:
        return Session(
            id=row[0],
            name=row[1],
            start_time=datetime.fromisoformat(row[2]),
            end_time=datetime.fromisoformat(row[3]) if row[3] else None,
            summary=row[4] or "",
            files_changed=json.loads(row[5] or "[]"),
        )

    def get_session(self, session_id: str) -> Session | None:
        """Get session by ID."""
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if not row:
            return None
        return self._session_from_row(row)

    def get_recent_sessions(self, limit: int = 10) -> list[Session]:
        """Get recent sessions."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM sessions
                ORDER BY start_time DESC
                LIMIT ?
            """,
                (limit,),
            ).fetchall()
        return [self._session_from_row(row) for row in rows]

    def add_decision(
        self,
        session_id: str,
        decision_type: DecisionType,
        description: str,
        rationale: str = "",
        files_affected: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Decision:
        """Add a decision to a session."""
        decision_id = (
            f"decision_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            f"_{uuid.uuid4().hex[:6]}"
        )
        timestamp = datetime.now()

        with self._lock:
            self.conn.execute(
                """
                INSERT INTO decisions (id, session_id, decision_type, description,
                                       rationale, files_affected, timestamp, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    decision_id,
                    session_id,
                    decision_type.value,
                    description,
                    rationale,
                    json.dumps(files_affected or []),
                    timestamp.isoformat(),
                    json.dumps(tags or []),
                ),
            )
            self.conn.commit()

        return Decision(
            id=decision_id,
            session_id=session_id,
            decision_type=decision_type,
            description=description,
            rationale=rationale,
            files_affected=files_affected or [],
            timestamp=timestamp,
            tags=tags or [],
        )

    @staticmethod
    def _decision_from_row(row) -> Decision:
        try:
            timestamp = datetime.fromisoformat(row[6])
        except (TypeError, ValueError):
            timestamp = datetime.now()
        return Decision(
            id=row[0],
            session_id=row[1],
            decision_type=_coerce_decision_type(row[2]),
            description=row[3],
            rationale=row[4] or "",
            files_affected=json.loads(row[5] or "[]"),
            timestamp=timestamp,
            tags=json.loads(row[7] or "[]"),
        )

    def get_decisions(self, session_id: str) -> list[Decision]:
        """Get all decisions in a session."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM decisions
                WHERE session_id = ?
                ORDER BY timestamp
            """,
                (session_id,),
            ).fetchall()
        return [self._decision_from_row(row) for row in rows]

    def search_decisions(self, query: str, limit: int = 50) -> list[Decision]:
        """Search decisions by description and rationale."""
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM decisions
                WHERE description LIKE ? ESCAPE '\\'
                   OR rationale LIKE ? ESCAPE '\\'
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (pattern, pattern, limit),
            ).fetchall()
        return [self._decision_from_row(row) for row in rows]

    def add_memory(self, session_id: str, key: str, value: str, context: str = ""):
        """Add a memory entry."""
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO memories (session_id, key, value, context)
                VALUES (?, ?, ?, ?)
            """,
                (session_id, key, value, context),
            )
            self.conn.commit()

    def get_memories(self, session_id: str) -> list[dict]:
        """Get all memories for a session.

        Note: ``timestamp`` values come from SQLite's CURRENT_TIMESTAMP and
        are UTC, unlike session/decision timestamps which are naive local —
        don't compare them directly.
        """
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM memories
                WHERE session_id = ?
                ORDER BY timestamp
            """,
                (session_id,),
            ).fetchall()

        return [
            {"id": row[0], "key": row[2], "value": row[3], "context": row[4], "timestamp": row[5]}
            for row in rows
        ]

    def search_memories(self, query: str, limit: int = 50) -> list[dict]:
        """Search memories by key, value or context."""
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM memories
                WHERE key LIKE ? ESCAPE '\\'
                   OR value LIKE ? ESCAPE '\\'
                   OR context LIKE ? ESCAPE '\\'
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (pattern, pattern, pattern, limit),
            ).fetchall()

        return [
            {
                "id": row[0],
                "session_id": row[1],
                "key": row[2],
                "value": row[3],
                "context": row[4],
                "timestamp": row[5],
            }
            for row in rows
        ]

    def record_file_change(
        self, session_id: str, file_path: str, change_type: str, line_count: int = 0
    ):
        """Record a file change."""
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO file_changes (session_id, file_path, change_type, line_count)
                VALUES (?, ?, ?, ?)
            """,
                (session_id, file_path, change_type, line_count),
            )
            self.conn.commit()

    def get_file_changes(self, session_id: str) -> list[dict]:
        """Get file changes for a session."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT * FROM file_changes
                WHERE session_id = ?
                ORDER BY timestamp
            """,
                (session_id,),
            ).fetchall()

        return [
            {
                "id": row[0],
                "file_path": row[2],
                "change_type": row[3],
                "line_count": row[4],
                "timestamp": row[5],
            }
            for row in rows
        ]

    def generate_session_summary(self, session_id: str) -> str:
        """Generate a summary for a session."""
        session = self.get_session(session_id)
        if not session:
            return ""

        decisions = self.get_decisions(session_id)
        file_changes = self.get_file_changes(session_id)

        summary_parts = []

        # Session info
        duration = ""
        if session.end_time:
            delta = session.end_time - session.start_time
            minutes = int(delta.total_seconds() / 60)
            duration = f" ({minutes} minutes)"

        summary_parts.append(f"Session: {session.name}{duration}")

        # Statistics
        summary_parts.append(f"Decisions made: {len(decisions)}")
        summary_parts.append(f"Files changed: {len(file_changes)}")

        # Decision breakdown
        if decisions:
            type_counts = {}
            for d in decisions:
                type_counts[d.decision_type.value] = type_counts.get(d.decision_type.value, 0) + 1

            type_summary = ", ".join([f"{k}: {v}" for k, v in type_counts.items()])
            summary_parts.append(f"Decision types: {type_summary}")

        # Key decisions
        if decisions:
            summary_parts.append("\nKey decisions:")
            for d in decisions[:5]:
                summary_parts.append(f"  - [{d.decision_type.value}] {d.description}")

        # Files affected
        if file_changes:
            unique_files = list({fc["file_path"] for fc in file_changes})
            summary_parts.append(f"\nFiles affected: {len(unique_files)}")
            for f in unique_files[:5]:
                summary_parts.append(f"  - {f}")

        return "\n".join(summary_parts)

    def get_statistics(self) -> dict:
        """Get overall statistics."""
        with self._lock:
            session_count = self.conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            decision_count = self.conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
            memory_count = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            file_change_count = self.conn.execute(
                "SELECT COUNT(*) FROM file_changes"
            ).fetchone()[0]
            decision_types = self.conn.execute("""
                SELECT decision_type, COUNT(*)
                FROM decisions
                GROUP BY decision_type
            """).fetchall()

        return {
            "sessions": session_count,
            "decisions": decision_count,
            "memories": memory_count,
            "file_changes": file_change_count,
            "decision_types": {row[0]: row[1] for row in decision_types},
        }

    def close(self):
        """Close database connection."""
        with self._lock:
            self.conn.close()

    def __enter__(self) -> "SessionMemory":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


# Global memory instance
_global_memory: SessionMemory | None = None


def get_memory(db_path: Path | None = None) -> SessionMemory:
    """Get or create global memory instance.

    An explicit ``db_path`` differing from the current singleton's path
    re-creates the singleton against the requested database instead of being
    silently ignored.
    """
    global _global_memory
    if db_path is None:
        db_path = Path.cwd() / ".codenexus" / "memory.db"

    if _global_memory is None or _global_memory.db_path != Path(db_path):
        if _global_memory is not None:
            _global_memory.close()
        _global_memory = SessionMemory(db_path)
    return _global_memory
