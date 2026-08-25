"""Tree-sitter based code parser with regex fallback."""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .graph import Edge, Node

logger = logging.getLogger(__name__)

# Try to import tree-sitter
try:
    from tree_sitter_languages import get_parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


@dataclass
class ParsePattern:
    """Pattern for extracting symbols (regex fallback)."""

    function_pattern: str
    class_pattern: str
    import_patterns: list[str]
    # Languages whose blocks are delimited by braces rather than indentation.
    braced: bool = False


# Regex patterns for fallback
REGEX_PATTERNS = {
    "python": ParsePattern(
        function_pattern=r"^(?:async\s+)?def\s+(\w+)\s*\([^)]*\)(?:\s*->[^:]+)?:",
        class_pattern=r"^class\s+(\w+)(?:\([^)]*\))?:",
        import_patterns=[
            r"^import\s+(.+)",
            r"^from\s+(\S+)\s+import",
        ],
    ),
    "javascript": ParsePattern(
        function_pattern=r"^(?:async\s+)?function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>)",
        class_pattern=r"^class\s+(\w+)",
        import_patterns=[
            r'^import\s+.+\s+from\s+["\'](.+?)["\']',
            r'^import\s+["\'](.+?)["\']',
            r'^const\s+.+\s+require\(["\'](.+?)["\']\)',
        ],
        braced=True,
    ),
    "typescript": ParsePattern(
        function_pattern=r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>)",
        class_pattern=r"^(?:export\s+)?class\s+(\w+)",
        import_patterns=[
            r'^import\s+.+\s+from\s+["\'](.+?)["\']',
            r'^import\s+["\'](.+?)["\']',
        ],
        braced=True,
    ),
    "go": ParsePattern(
        function_pattern=r"^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(",
        class_pattern=r"^type\s+(\w+)\s+struct",
        import_patterns=[
            r'^import\s+[\(]?\s*["\'](.+?)["\']',
            r'^import\s+["\'](.+?)["\']',
            r'^["\']([^"\']+)["\']\s*(?://.*)?$',  # entries inside a grouped import block
        ],
        braced=True,
    ),
    "rust": ParsePattern(
        function_pattern=r"^(?:pub(?:\(.*?\))?\s+)?(?:async\s+)?fn\s+(\w+)",
        class_pattern=r"^(?:pub(?:\(.*?\))?\s+)?struct\s+(\w+)|(?:pub(?:\(.*?\))?\s+)?enum\s+(\w+)",
        import_patterns=[
            r"^use\s+(.+?)::",
            r"^use\s+\{(.+?)\}",
        ],
        braced=True,
    ),
    "java": ParsePattern(
        function_pattern=r"(?:public|private|protected|static|\s)*[\w<>\[\]]+\s+(\w+)\s*\(",
        class_pattern=r"(?:public|private|protected)\s+(?:abstract\s+)?class\s+(\w+)",
        import_patterns=[
            r"^import\s+(.+?)\s*;",
        ],
        braced=True,
    ),
    "csharp": ParsePattern(
        function_pattern=r"(?:public|private|protected|internal|static|\s)*[\w<>\[\]]+\s+(\w+)\s*\(",
        class_pattern=r"(?:public|private|protected|internal)\s+(?:partial\s+)?(?:abstract\s+)?class\s+(\w+)",
        import_patterns=[
            r"^using\s+(.+?)\s*;",
        ],
        braced=True,
    ),
}


class CodeParser:
    """Parse source code using tree-sitter with regex fallback."""

    def __init__(self, use_tree_sitter: bool = True):
        self.use_tree_sitter = use_tree_sitter and TREE_SITTER_AVAILABLE
        self.parsers = {}

        if self.use_tree_sitter:
            self._init_tree_sitter()

    def _init_tree_sitter(self):
        """Initialize tree-sitter parsers."""
        languages = ["python", "javascript", "typescript", "go", "rust", "java", "csharp"]
        for lang in languages:
            try:
                self.parsers[lang] = get_parser(lang)
            except Exception:
                logger.debug("tree-sitter grammar unavailable for %s", lang)

    def _detect_language(self, file_path: Path) -> str | None:
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".cs": "csharp",
        }
        return ext_map.get(file_path.suffix.lower())

    @staticmethod
    def _read_source(file_path: Path) -> tuple[bytes, str]:
        """Read a source file returning (raw bytes stripped of BOM, decoded text).

        Decoding uses UTF-8 with BOM stripping so files saved by Windows
        editors (which prepend a BOM) do not break first-line anchors, and
        ``errors="replace"`` so non-UTF-8 locales degrade visibly instead of
        silently dropping characters.
        """
        raw = file_path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        return raw, raw.decode("utf-8", errors="replace")

    def parse_file(self, file_path: Path) -> tuple[list[Node], list[Edge]]:
        """Parse a file and return nodes and edges."""
        language = self._detect_language(file_path)
        if not language:
            return [], []

        try:
            source_bytes, source = self._read_source(file_path)

            # Try tree-sitter first
            if self.use_tree_sitter and language in self.parsers:
                return self._parse_with_tree_sitter(source_bytes, str(file_path), language)

            # Fallback to regex
            return self._parse_with_regex(source, str(file_path), language)
        except OSError as e:
            logger.warning("Error reading %s: %s", file_path, e)
            return [], []

    def _parse_with_tree_sitter(
        self, source_bytes: bytes, file_path: str, language: str
    ) -> tuple[list[Node], list[Edge]]:
        """Parse using tree-sitter AST.

        All slicing happens on ``source_bytes`` because tree-sitter offsets
        are byte offsets; slicing ``str`` with them corrupts any source
        containing multi-byte characters (e.g. CJK comments).
        """
        parser = self.parsers.get(language)
        if not parser:
            _, source = None, source_bytes.decode("utf-8", errors="replace")
            return self._parse_with_regex(source, file_path, language)

        tree = parser.parse(source_bytes)
        nodes = []
        edges = []

        def walk_node(node, depth=0):
            # Extract functions
            if node.type in (
                "function_definition",
                "function_declaration",
                "arrow_function",
                "function",
            ):
                name = self._get_node_name(node, source_bytes)
                if name:
                    node_id = f"{file_path}::{name}"
                    sig = self._extract_signature_tree_sitter(node, source_bytes)
                    content = self._slice_utf8(source_bytes, node.start_byte, node.end_byte)

                    nodes.append(
                        Node(
                            id=node_id,
                            file_path=file_path,
                            name=name,
                            node_type="function",
                            start_line=node.start_point[0],
                            end_line=node.end_point[0],
                            content=content,
                            signature=sig,
                        )
                    )

            # Extract classes
            elif node.type in ("class_definition", "class_declaration", "class"):
                name = self._get_node_name(node, source_bytes)
                if name:
                    node_id = f"{file_path}::{name}"
                    sig = self._extract_signature_tree_sitter(node, source_bytes)
                    content = self._slice_utf8(source_bytes, node.start_byte, node.end_byte)

                    nodes.append(
                        Node(
                            id=node_id,
                            file_path=file_path,
                            name=name,
                            node_type="class",
                            start_line=node.start_point[0],
                            end_line=node.end_point[0],
                            content=content,
                            signature=sig,
                        )
                    )

            # Extract imports
            elif node.type in ("import_statement", "import_from_statement", "import_declaration"):
                imp = self._slice_utf8(source_bytes, node.start_byte, node.end_byte)
                edges.append(
                    Edge(
                        source_id=f"{file_path}::import", target_id=imp.strip(), edge_type="imports"
                    )
                )

            # Recurse
            for child in node.children:
                walk_node(child, depth + 1)

        walk_node(tree.root_node)
        return nodes, edges

    @staticmethod
    def _slice_utf8(src: bytes, start: int, end: int) -> str:
        """Decode a byte range of source into text safely."""
        return src[start:end].decode("utf-8", errors="replace")

    def _get_node_name(self, node, source_bytes: bytes) -> str | None:
        """Extract name from AST node."""
        # Try common name fields
        for field in ["name", "identifier"]:
            name_node = node.child_by_field_name(field)
            if name_node:
                return self._slice_utf8(source_bytes, name_node.start_byte, name_node.end_byte)

        # Arrow functions are usually bound through an enclosing assignment;
        # naming them after their first parameter made ids meaningless.
        parent = node.parent
        depth = 0
        while parent is not None and depth < 5:
            if parent.type == "variable_declarator":
                name_node = parent.child_by_field_name("name")
                if name_node:
                    return self._slice_utf8(source_bytes, name_node.start_byte, name_node.end_byte)
            parent = parent.parent
            depth += 1

        # Try first identifier child
        for child in node.children:
            if child.type == "identifier":
                return self._slice_utf8(source_bytes, child.start_byte, child.end_byte)

        return None

    def _extract_signature_tree_sitter(self, node, source_bytes: bytes) -> str:
        """Extract signature from tree-sitter node."""
        # Get text up to the body/block
        sig_end = node.end_byte
        for child in node.children:
            if child.type in (
                "block",
                "statement_block",
                "class_body",
                "arrow_function",
                "function_body",
            ):
                sig_end = child.start_byte
                break

        sig = self._slice_utf8(source_bytes, node.start_byte, sig_end).strip()
        sig = re.sub(r"\s+", " ", sig)
        if sig.endswith(":"):
            sig = sig[:-1].strip()
        elif sig.endswith("=>"):
            sig = sig[:-2].strip()

        return sig + " ..."

    def _parse_with_regex(
        self, source: str, file_path: str, language: str
    ) -> tuple[list[Node], list[Edge]]:
        """Fallback regex-based parsing."""
        nodes = []
        edges = []

        patterns = REGEX_PATTERNS.get(language)
        if not patterns:
            return [], []

        lines = source.split("\n")

        # Pre-collect class names so constructors (Java/C#: ``public Foo(``)
        # inside ``class Foo``) don't emit a function node whose id collides
        # with the class node and overwrites it.
        class_names: set[str] = set()
        for line in lines:
            m = re.match(patterns.class_pattern, line.strip())
            if m:
                for idx in (1, 2):
                    if m.lastindex and m.lastindex >= idx and m.group(idx):
                        class_names.add(m.group(idx))
                        break

        in_go_import_block = False
        seen_ids: set[str] = set()

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Skip obvious comments so commented-out code doesn't create
            # phantom symbols.
            if stripped.startswith(("#", "//", "*", "/*")):
                continue

            # Track Go grouped-import blocks so inner entries are matched by
            # their dedicated pattern without leaking it to other contexts.
            go_block_entry = False
            if language == "go":
                if re.match(r"^import\s*\(", stripped):
                    in_go_import_block = True
                    continue
                if in_go_import_block:
                    if stripped.startswith(")"):
                        in_go_import_block = False
                        continue
                    go_block_entry = bool(re.match(r'^["\']', stripped))

            # Check for functions
            match = re.match(patterns.function_pattern, stripped)
            if match:
                name = None
                for idx in (1, 2):
                    if match.lastindex and match.lastindex >= idx and match.group(idx):
                        name = match.group(idx)
                        break
                if name:
                    # Constructor shadowing its class: skip to keep ids unique.
                    if name in class_names:
                        continue
                    node_id = f"{file_path}::{name}"
                    if node_id in seen_ids:
                        continue
                    seen_ids.add(node_id)
                    nodes.append(
                        Node(
                            id=node_id,
                            file_path=file_path,
                            name=name,
                            node_type="function",
                            start_line=i,
                            end_line=self._find_block_end(lines, i, patterns.braced),
                            content=self._extract_block(lines, i, patterns.braced),
                            signature=self._extract_signature_regex(lines, i, patterns.braced),
                        )
                    )

            # Check for classes
            match = re.match(patterns.class_pattern, stripped)
            if match:
                name = None
                for idx in (1, 2):
                    if match.lastindex and match.lastindex >= idx and match.group(idx):
                        name = match.group(idx)
                        break
                if name:
                    node_id = f"{file_path}::{name}"
                    if node_id not in seen_ids:
                        seen_ids.add(node_id)
                        nodes.append(
                            Node(
                                id=node_id,
                                file_path=file_path,
                                name=name,
                                node_type="class",
                                start_line=i,
                                end_line=self._find_block_end(lines, i, patterns.braced),
                                content=self._extract_block(lines, i, patterns.braced),
                                signature=self._extract_class_signature_regex(lines, i),
                            )
                        )

            # Check for imports
            for import_pattern in patterns.import_patterns:
                # The grouped-entry pattern only applies inside Go import blocks.
                if language == "go" and import_pattern.startswith('["\\\']') and not go_block_entry:
                    continue
                match = re.match(import_pattern, stripped)
                if match:
                    imp = match.group(1).strip()
                    edges.append(
                        Edge(
                            source_id=f"{file_path}::import",
                            target_id=imp,
                            edge_type="imports",
                        )
                    )
                    break

        return nodes, edges

    def _extract_signature_regex(self, lines: list[str], start: int, braced: bool) -> str:
        """Extract a function signature; stops at ':', '{' or ';'."""
        sig_lines = []
        for i in range(start, min(start + 5, len(lines))):
            text = lines[i].rstrip()
            sig_lines.append(text)
            if text.endswith(":") or text.endswith(";") or "{" in text or "=>" in text:
                break
        joined = " ".join(part.strip() for part in sig_lines).strip()
        if braced:
            # Trim everything from the opening brace onward.
            brace_pos = joined.find("{")
            if brace_pos != -1:
                joined = joined[:brace_pos].strip()
        return joined + " ..."

    def _extract_class_signature_regex(self, lines: list[str], start: int) -> str:
        """Extract class signature using regex."""
        sig_lines = []
        for i in range(start, min(start + 5, len(lines))):
            text = lines[i].rstrip()
            sig_lines.append(text)
            if text.endswith(":") or text.endswith(";") or "{" in text:
                break
        joined = " ".join(part.strip() for part in sig_lines).strip()
        brace_pos = joined.find("{")
        if brace_pos != -1:
            joined = joined[:brace_pos].strip()
        return joined + " ..."

    def _find_block_end(self, lines: list[str], start: int, braced: bool = False) -> int:
        """Find the end of a code block.

        Braced languages (JS/TS/Go/Rust/Java/C#) use brace counting; Python
        uses indentation. Previously the indentation heuristic ran for every
        language, truncating C-like blocks early.
        """
        if start >= len(lines):
            return start

        if braced:
            balance = 0
            opened = False
            for i in range(start, len(lines)):
                balance += lines[i].count("{") - lines[i].count("}")
                if "{" in lines[i]:
                    opened = True
                if opened and balance <= 0:
                    return i
            return len(lines) - 1

        first_line = lines[start]
        base_indent = len(first_line) - len(first_line.lstrip())

        for i in range(start + 1, len(lines)):
            line = lines[i]
            if line.strip() == "":
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent:
                return i - 1

        return len(lines) - 1

    def _extract_block(self, lines: list[str], start: int, braced: bool = False) -> str:
        """Extract code block content."""
        end = self._find_block_end(lines, start, braced)
        return "\n".join(lines[start : end + 1])


def create_capsule(source: str, skeleton_ratio: float = 0.9) -> str:
    """Create a capsule: full source for pivot, skeleton for others.

    Note: ``skeleton_ratio`` is currently reserved; the skeleton always keeps
    imports, definitions and comments.
    """
    lines = source.split("\n")
    skeleton_lines = []

    for line in lines:
        stripped = line.strip()
        # Keep imports (Python + JS-family + Go/Rust/Java/C# forms)
        if stripped.startswith(("import ", "from ", "#include", "using ", "use ")):
            skeleton_lines.append(line)
        # Keep function/class definitions (skeleton)
        elif stripped.startswith(("def ", "function ", "class ", "async def ", "fn ", "struct ", "enum ", "type ")):
            skeleton_lines.append(line)
            skeleton_lines.append("    ...")
        # Keep comments
        elif stripped.startswith("#") or stripped.startswith("//"):
            skeleton_lines.append(line)

    return "\n".join(skeleton_lines)
