"""Resolve import statements into real graph edges.

Before this module existed, every import edge pointed from a ``{path}::import``
pseudo-node to raw statement text, so no edge ever connected two real node
ids — PageRank, impact analysis and dependents queries were structurally
empty. The resolver gives every indexed file a *module* node and rewrites
each import statement into an edge between real nodes:

``import a.b``            -> ``a/b.py::module`` (or its ``__init__.py``)
``from a.b import Foo``   -> ``Foo``'s symbol node inside ``a/b.py`` when found
``./utils`` (JS/TS)       -> ``utils.ts::module`` etc.
``use crate::x::y``       -> ``x/y.rs::module``
``com.x.y.Z`` (Java/C#)   -> ``.../y/Z.(java|cs)::module``

Unresolvable imports (external packages, stdlib) are dropped rather than
kept as noise.
"""

import logging
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

from .graph import Edge, Node
from .parser import REGEX_PATTERNS

logger = logging.getLogger(__name__)

# Extensions consulted when resolving extension-less specifiers per language.
_EXT_CANDIDATES = {
    "python": [".py"],
    "javascript": [".js", ".jsx", ".mjs", ".cjs"],
    "typescript": [".ts", ".tsx", ".js", ".jsx"],
    "go": [".go"],
    "rust": [".rs"],
    "java": [".java"],
    "csharp": [".cs"],
}

# Segment prefixes that carry no path information in their language.
_RUST_IGNORED_SEGMENTS = {"crate", "self", "super"}

# Matches ``from a.b import X as Y, Z`` style statements so symbol-level
# resolution can kick in.
_PY_FROM_RE = re.compile(r"^from\s+(\S+)\s+import\s+(.+)$")


@dataclass
class FileEntry:
    """One indexed source file handed to the resolver."""

    abs_path: Path
    # Path form used inside node ids/file paths (may carry a repo alias
    # prefix, e.g. "api/src/app.py"); always forward-slash separated.
    rel_path: str
    language: str
    # Symbol name -> node id for top-level defs discovered by the parser.
    symbols: dict[str, str] = field(default_factory=dict)
    # Raw import statement texts collected from the parser.
    raw_imports: list[str] = field(default_factory=list)

    def raw_import_statements(self) -> list[str]:
        return self.raw_imports

    @property
    def module_id(self) -> str:
        return f"{self.rel_path}::module"


class ImportResolver:
    """Rewrites raw import statements into edges between real node ids."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self._by_rel: dict[str, FileEntry] = {}
        self._by_rel_lower: dict[str, FileEntry] = {}
        self._by_stem: dict[str, list[FileEntry]] = {}
        self._entries: list[FileEntry] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build(self, entries: list[FileEntry]) -> tuple[list[Node], list[Edge]]:
        """Create module nodes for all entries plus resolved import edges."""
        self._entries = entries
        for entry in entries:
            norm = self._normalize(entry.rel_path)
            self._by_rel[norm] = entry
            self._by_rel_lower.setdefault(norm.lower(), entry)
            self._by_stem.setdefault(Path(norm).stem.lower(), []).append(entry)

        module_nodes = [
            Node(
                id=e.module_id,
                file_path=e.rel_path,
                name=self._display_name(e),
                node_type="module",
                start_line=0,
                end_line=0,
                content="",
                signature=f"module {e.rel_path}",
            )
            for e in entries
        ]

        edges: list[Edge] = []
        seen: set[tuple[str, str]] = set()
        for entry in entries:
            patterns = REGEX_PATTERNS.get(entry.language)
            if patterns is None:
                continue
            for stmt in entry.raw_import_statements():
                for spec, symbol in self._extract_specifiers(stmt, entry.language, patterns):
                    target = self._resolve(spec, symbol, entry)
                    if target is None or target == entry.module_id:
                        continue
                    key = (entry.module_id, target)
                    if key not in seen:
                        seen.add(key)
                        edges.append(
                            Edge(
                                source_id=entry.module_id,
                                target_id=target,
                                edge_type="imports",
                            )
                        )

        logger.info(
            "Resolved %d import edges across %d files", len(edges), len(entries)
        )
        return module_nodes, edges

    # ------------------------------------------------------------------
    # Specifier extraction
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_specifiers(statement: str, language: str, patterns) -> list[tuple[str, str | None]]:
        """Pull (specifier, optional symbol) pairs out of one import statement.

        Handles multi-line tree-sitter statements (e.g. Go grouped imports)
        by scanning line by line.
        """
        results: list[tuple[str, str | None]] = []
        lines = statement.split("\n") if "\n" in statement else [statement]

        py_from = None
        if language == "python":
            py_from = _PY_FROM_RE.match(statement.strip())

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            for pattern in patterns.import_patterns:
                m = re.match(pattern, stripped)
                if m and m.lastindex:
                    spec = m.group(1).strip().strip('"\'').rstrip(";").strip()
                    if spec:
                        results.append((spec, None))
                    break

        # Regex-fallback parsers emit bare specifiers ("os.path", "./utils")
        # instead of full statements; accept those directly when nothing else
        # matched.
        bare_re = re.compile(r"^[.\w][\w./\-]*$")
        for line in lines:
            stripped = line.strip().strip("\"'").rstrip(";").strip()
            if stripped and bare_re.match(stripped):
                results.append((stripped, None))

        # Symbol-level resolution for Python ``from X import a, b``.
        if py_from:
            module_spec = py_from.group(1)
            imported = py_from.group(2)
            if imported.strip().startswith("("):
                imported = imported.strip()[1:]
            imported = imported.rstrip(")").strip()
            for name in imported.split(","):
                name = name.strip().split(" as ")[0].strip()
                if name and not name.startswith("*"):
                    results.append((module_spec, name))
        elif language == "python":
            for stmt_line in [statement.strip()]:
                plain = re.match(r"^import\s+(.+)$", stmt_line)
                if plain:
                    for part in plain.group(1).split(","):
                        spec = part.strip().split(" as ")[0].strip()
                        if spec:
                            results.append((spec, None))

        return results

    # ------------------------------------------------------------------
    # Resolution strategies
    # ------------------------------------------------------------------
    def _resolve(self, spec: str, symbol: str | None, importer: FileEntry) -> str | None:
        lang = importer.language

        if lang == "python":
            rel_file = self._resolve_python(spec, importer)
        elif lang in ("javascript", "typescript"):
            rel_file = self._resolve_js_ts(spec, importer)
        elif lang == "rust":
            rel_file = self._resolve_dotted(spec.replace("::", "."), importer, ".rs")
        elif lang in ("java", "csharp"):
            rel_file = self._resolve_dotted(spec, importer, ".java" if lang == "java" else ".cs")
        else:  # go
            rel_file = self._resolve_go(spec)

        if rel_file is None:
            return None

        entry = self._lookup_rel(rel_file)
        if entry is None:
            return None

        # Prefer the imported symbol's own node when we have it.
        if symbol is not None:
            node_id = entry.symbols.get(symbol)
            if node_id is not None:
                return node_id
        return entry.module_id

    def _resolve_python(self, spec: str, importer: FileEntry) -> str | None:
        leading_dots = len(spec) - len(spec.lstrip("."))
        body = spec[leading_dots:]

        # Walk up from the importer's directory for each leading dot.
        base = posixpath.dirname(self._normalize(importer.rel_path))
        for _ in range(max(leading_dots - 1, 0)):
            base = posixpath.dirname(base)

        parts = body.split(".") if body else []
        # Try longest-to-shortest module paths: ``from pkg.mod import Name``
        # may refer to pkg/mod.py or to attribute ``Name`` living in pkg.py.
        for depth in range(len(parts), 0, -1):
            candidate_base = posixpath.join(base, *parts[:depth]) if depth else base
            joined = posixpath.normpath(candidate_base) if candidate_base else ""
            for cand in (joined + ".py", posixpath.join(joined, "__init__.py")):
                if self._lookup_rel(cand):
                    return cand
        return None

    def _resolve_js_ts(self, spec: str, importer: FileEntry) -> str | None:
        if not spec.startswith("."):
            return None  # bare npm-style specifier: treated as external

        base = posixpath.dirname(self._normalize(importer.rel_path))
        target = posixpath.normpath(posixpath.join(base, spec))
        # Strip a trailing extension the author wrote explicitly.
        stem_ext = posixpath.splitext(target)[1]
        if stem_ext in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"):
            target = target[: -len(stem_ext)]

        for ext in _EXT_CANDIDATES["typescript"]:
            if self._lookup_rel(target + ext):
                return target + ext
        for index_name in ("index.ts", "index.tsx", "index.js", "index.jsx"):
            cand = posixpath.join(target, index_name)
            if self._lookup_rel(cand):
                return cand
        return None

    def _resolve_go(self, spec: str) -> str | None:
        last = spec.rstrip("/").split("/")[-1]
        for entry in self._by_stem.get(last.lower(), []):
            return self._normalize(entry.rel_path)
        return None

    def _resolve_dotted(self, spec: str, importer: FileEntry, ext: str) -> str | None:
        """Resolve dotted/segmented specs (Rust, Java, C#) by suffix matching.

        Tries increasingly long suffixes of the specifier as directory +
        file-name layouts: ``com.x.y.Z`` -> ``y/Z.java`` -> ``x/y/Z.java`` ...
        """
        segments = [s for s in spec.split(".") if s]
        rust_mode = ext == ".rs"
        if rust_mode:
            segments = [s for s in segments if s not in _RUST_IGNORED_SEGMENTS]
        if not segments:
            return None

        max_depth = min(len(segments), 4)
        for depth in range(1, max_depth + 1):
            tail = segments[-depth:]
            candidate = "/".join(tail[:-1]) + "/" + tail[-1] + ext if len(tail) > 1 else tail[0] + ext
            if self._lookup_rel(candidate):
                return candidate
            # Rust allows module dirs: services/auth.rs or services/auth/mod.rs
            mod_candidate = "/".join(tail) + ext
            if self._lookup_rel(mod_candidate):
                return mod_candidate
            if rust_mode:
                init_candidate = "/".join(tail) + "/mod.rs"
                if self._lookup_rel(init_candidate):
                    return init_candidate
        return None

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------
    def _normalize(self, rel_path: str) -> str:
        return posixpath.normpath(rel_path.replace("\\", "/"))

    def _lookup_rel(self, rel: str) -> FileEntry | None:
        norm = self._normalize(rel)
        hit = self._by_rel.get(norm)
        if hit:
            return hit
        # Windows paths may differ in case from specifier-derived candidates.
        return self._by_rel_lower.get(norm.lower())

    @staticmethod
    def _display_name(entry: FileEntry) -> str:
        return Path(entry.rel_path).stem or entry.rel_path
