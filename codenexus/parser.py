"""Tree-sitter based code parser with regex fallback."""

import re
from dataclasses import dataclass
from pathlib import Path

from .graph import Edge, Node

# Try to import tree-sitter
try:
    import tree_sitter as _ts  # noqa: F401
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
    ),
    "typescript": ParsePattern(
        function_pattern=r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>)",
        class_pattern=r"^(?:export\s+)?class\s+(\w+)",
        import_patterns=[
            r'^import\s+.+\s+from\s+["\'](.+?)["\']',
            r'^import\s+["\'](.+?)["\']',
        ],
    ),
    "go": ParsePattern(
        function_pattern=r"^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(",
        class_pattern=r"^type\s+(\w+)\s+struct",
        import_patterns=[
            r'^import\s+[\(]?\s*["\'](.+?)["\']',
            r'^import\s+["\'](.+?)["\']',
        ],
    ),
    "rust": ParsePattern(
        function_pattern=r"^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)",
        class_pattern=r"^(?:pub\s+)?struct\s+(\w+)|(?:pub\s+)?enum\s+(\w+)",
        import_patterns=[
            r"^use\s+(.+?)::",
            r"^use\s+\{(.+?)\}",
        ],
    ),
    "java": ParsePattern(
        function_pattern=r"(?:public|private|protected|static|\s)*[\w<>\[\]]+\s+(\w+)\s*\(",
        class_pattern=r"(?:public|private|protected)\s+(?:abstract\s+)?class\s+(\w+)",
        import_patterns=[
            r"^import\s+(.+?)\s*;",
        ],
    ),
    "csharp": ParsePattern(
        function_pattern=r"(?:public|private|protected|internal|static|\s)*[\w<>\[\]]+\s+(\w+)\s*\(",
        class_pattern=r"(?:public|private|protected|internal)\s+(?:partial\s+)?(?:abstract\s+)?class\s+(\w+)",
        import_patterns=[
            r"^using\s+(.+?)\s*;",
        ],
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
                pass

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

    def parse_file(self, file_path: Path) -> tuple[list[Node], list[Edge]]:
        """Parse a file and return nodes and edges."""
        language = self._detect_language(file_path)
        if not language:
            return [], []

        try:
            source = file_path.read_text(encoding="utf-8", errors="ignore")

            # Try tree-sitter first
            if self.use_tree_sitter and language in self.parsers:
                return self._parse_with_tree_sitter(source, str(file_path), language)

            # Fallback to regex
            return self._parse_with_regex(source, str(file_path), language)
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return [], []

    def _parse_with_tree_sitter(
        self, source: str, file_path: str, language: str
    ) -> tuple[list[Node], list[Edge]]:
        """Parse using tree-sitter AST."""
        parser = self.parsers.get(language)
        if not parser:
            return self._parse_with_regex(source, file_path, language)

        tree = parser.parse(bytes(source, "utf-8"))
        nodes = []
        edges = []

        # Track the enclosing definition so calls can be attributed to a caller
        current_def_stack: list[str] = []

        def walk_node(node, depth=0):
            # Extract functions
            if node.type in (
                "function_definition",
                "function_declaration",
                "arrow_function",
                "function",
                "method_definition",
            ):
                name = self._get_node_name(node, source)
                if name:
                    node_id = name
                    sig = self._extract_signature_tree_sitter(node, source)
                    content = source[node.start_byte : node.end_byte]

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
                    current_def_stack.append(node_id)
                    for child in node.children:
                        walk_node(child, depth + 1)
                    current_def_stack.pop()
                    return

            # Extract classes
            elif node.type in (
                "class_definition",
                "class_declaration",
                "class",
            ):
                name = self._get_node_name(node, source)
                if name:
                    node_id = name
                    sig = self._extract_signature_tree_sitter(node, source)
                    content = source[node.start_byte : node.end_byte]

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
                    current_def_stack.append(node_id)
                    for child in node.children:
                        walk_node(child, depth + 1)
                    current_def_stack.pop()
                    return

            # Extract imports
            elif node.type in (
                "import_statement",
                "import_from_statement",
                "import_declaration",
            ):
                imp = source[node.start_byte : node.end_byte]
                edges.append(
                    Edge(
                        source_id=f"{file_path}::import",
                        target_id=imp.strip(),
                        edge_type="imports",
                    )
                )
                for child in node.children:
                    walk_node(child, depth + 1)
                return

            # Extract function/method calls -> call edges
            elif node.type in (
                "call",
                "call_expression",
                "function_call",
                "method_invocation",
                "invocation_expression",
            ):
                callee = self._get_callee_name(node, source)
                if callee and current_def_stack:
                    caller_id = current_def_stack[-1]
                    edges.append(
                        Edge(
                            source_id=caller_id,
                            target_id=callee,
                            edge_type="calls",
                        )
                    )
                for child in node.children:
                    walk_node(child, depth + 1)
                return

            # Recurse
            for child in node.children:
                walk_node(child, depth + 1)

        walk_node(tree.root_node)
        return nodes, edges

    def _get_callee_name(self, node, source: str) -> str | None:
        """Extract the callee name from a call/invocation node."""
        # Common shapes:
        #   call_expression: function(...)  -> child[0] is identifier/field_expression
        #   method_invocation: obj.method(...) -> field_expression name
        #   function_call: name(...) (Go/Java/Rust-ish)
        target = None
        for child in node.children:
            if child.type in (
                "identifier",
                "field_expression",
                "selector_expression",
                "member_expression",
                "scoped_identifier",
                "qualified_identifier",
            ):
                target = child
                break
        if target is None:
            return None

        if target.type in ("identifier",):
            return source[target.start_byte : target.end_byte]

        if target.type in (
            "field_expression",
            "member_expression",
            "selector_expression",
        ):
            # Take the last identifier segment (e.g. obj.method -> method)
            last = None
            for c in target.children:
                if c.type == "identifier":
                    last = c
            if last is not None:
                return source[last.start_byte : last.end_byte]
            return source[target.start_byte : target.end_byte]

        if target.type in ("scoped_identifier", "qualified_identifier"):
            # module::func or a.b.c -> take the last segment
            text = source[target.start_byte : target.end_byte]
            return text.split("::")[-1].split(".")[-1]

        return None

    def _get_node_name(self, node, source: str) -> str | None:
        """Extract name from AST node."""
        # Try common name fields
        for field in ["name", "identifier"]:
            name_node = node.child_by_field_name(field)
            if name_node:
                return source[name_node.start_byte : name_node.end_byte]

        # Try first identifier child
        for child in node.children:
            if child.type == "identifier":
                return source[child.start_byte : child.end_byte]

        return None

    def _extract_signature_tree_sitter(self, node, source: str) -> str:
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

        sig = source[node.start_byte : sig_end].strip()
        if sig.endswith(":"):
            sig = sig[:-1].strip()
        elif sig.endswith("=>"):
            sig = sig[:-2].strip()

        return sig + " ..."

    def _parse_with_regex(
        self, source: str, file_path: str, language: str
    ) -> tuple[list[Node], list[Edge]]:
        """Fallback regex-based parsing.

        Extracts function/class definitions plus in-file call edges so that
        the dependency graph and PageRank centrality are meaningful even
        without tree-sitter.
        """
        nodes = []
        edges = []

        patterns = REGEX_PATTERNS.get(language)
        if not patterns:
            return [], []

        lines = source.split("\n")

        # First pass: find definitions and their block ranges
        defs: list[dict] = []  # {name, node_type, start, end, id}
        calls: list[tuple[int, str]] = []  # (line_index, raw_call_text)

        call_re = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Check for functions
            match = re.match(patterns.function_pattern, stripped, re.MULTILINE)
            if match:
                name = match.group(1) if match.lastindex >= 1 else None
                if not name and match.lastindex >= 2:
                    name = match.group(2)
                if name:
                    node_id = name
                    sig = self._extract_function_signature_regex(lines, i)
                    end = self._find_block_end(lines, i)
                    defs.append(
                        {
                            "name": name,
                            "node_type": "function",
                            "start": i,
                            "end": end,
                            "id": node_id,
                        }
                    )
                    nodes.append(
                        Node(
                            id=node_id,
                            file_path=file_path,
                            name=name,
                            node_type="function",
                            start_line=i,
                            end_line=end,
                            content=self._extract_block(lines, i),
                            signature=sig,
                        )
                    )

            # Check for classes
            match = re.match(patterns.class_pattern, stripped, re.MULTILINE)
            if match:
                name = match.group(1)
                if name:
                    node_id = name
                    sig = self._extract_class_signature_regex(lines, i)
                    end = self._find_block_end(lines, i)
                    defs.append(
                        {
                            "name": name,
                            "node_type": "class",
                            "start": i,
                            "end": end,
                            "id": node_id,
                        }
                    )
                    nodes.append(
                        Node(
                            id=node_id,
                            file_path=file_path,
                            name=name,
                            node_type="class",
                            start_line=i,
                            end_line=end,
                            content=self._extract_block(lines, i),
                            signature=sig,
                        )
                    )

            # Check for imports
            for import_pattern in patterns.import_patterns:
                match = re.match(import_pattern, stripped)
                if match:
                    imp = match.group(1)
                    edges.append(
                        Edge(
                            source_id=f"{file_path}::import",
                            target_id=imp,
                            edge_type="imports",
                        )
                    )
                    break

            # Collect call sites (any line that invokes something)
            for m in call_re.finditer(stripped):
                calls.append((i, m.group(1)))

        # Second pass: attribute calls to their enclosing definition
        def_name_set = {d["name"] for d in defs}
        for line_idx, callee in calls:
            # Find the innermost definition that contains this line
            enclosing = None
            for d in defs:
                if d["start"] <= line_idx <= d["end"]:
                    # Prefer the deepest (smallest range) enclosing def
                    if enclosing is None or (d["end"] - d["start"]) < (
                        enclosing["end"] - enclosing["start"]
                    ):
                        enclosing = d
            if enclosing is None or callee == enclosing["name"]:
                continue
            target_id = callee
            # Emit the call edge. If the callee is not defined in this file,
            # also register it as an external symbol node so the graph stays
            # connected across files (needed for meaningful PageRank).
            if callee not in def_name_set:
                nodes.append(
                    Node(
                        id=callee,
                        file_path="<external>",
                        name=callee,
                        node_type="external",
                        start_line=0,
                        end_line=0,
                        content="",
                        signature=callee,
                    )
                )
                def_name_set.add(callee)
            edges.append(
                Edge(
                    source_id=enclosing["id"],
                    target_id=target_id,
                    edge_type="calls",
                )
            )

        return nodes, edges

    def _extract_function_signature_regex(self, lines: list[str], start: int) -> str:
        """Extract function signature using regex."""
        sig_lines = []
        for i in range(start, min(start + 5, len(lines))):
            sig_lines.append(lines[i].rstrip())
            if lines[i].rstrip().endswith(":"):
                break
        return " ".join(sig_lines).strip() + " ..."

    def _extract_class_signature_regex(self, lines: list[str], start: int) -> str:
        """Extract class signature using regex."""
        sig_lines = []
        for i in range(start, min(start + 5, len(lines))):
            sig_lines.append(lines[i].rstrip())
            if lines[i].rstrip().endswith(":"):
                break
        return " ".join(sig_lines).strip() + " ..."

    def _find_block_end(self, lines: list[str], start: int) -> int:
        """Find the end of a code block."""
        if start >= len(lines):
            return start

        # Get indentation of first line
        first_line = lines[start]
        base_indent = len(first_line) - len(first_line.lstrip())

        # Find where indentation returns to base level
        for i in range(start + 1, len(lines)):
            line = lines[i]
            if line.strip() == "":
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent:
                return i - 1

        return len(lines) - 1

    def _extract_block(self, lines: list[str], start: int) -> str:
        """Extract code block content."""
        end = self._find_block_end(lines, start)
        return "\n".join(lines[start : end + 1])


def create_capsule(source: str, skeleton_ratio: float = 0.9) -> str:
    """Create a capsule: full source for pivot, skeleton for others."""
    lines = source.split("\n")
    skeleton_lines = []

    for line in lines:
        stripped = line.strip()
        # Keep imports
        if stripped.startswith(("import ", "from ")):
            skeleton_lines.append(line)
        # Keep function/class definitions (skeleton)
        elif stripped.startswith(("def ", "function ", "class ", "async def ")):
            skeleton_lines.append(line)
            skeleton_lines.append("    ...")
        # Keep comments
        elif stripped.startswith("#") or stripped.startswith("//"):
            skeleton_lines.append(line)

    return "\n".join(skeleton_lines)
