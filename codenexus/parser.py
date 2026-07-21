"""Tree-sitter based code parser with regex fallback."""

import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from .graph import Node, Edge

# Try to import tree-sitter
try:
    import tree_sitter as ts
    from tree_sitter_languages import get_parser, get_language
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
        ]
    ),
    "javascript": ParsePattern(
        function_pattern=r"^(?:async\s+)?function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>)",
        class_pattern=r"^class\s+(\w+)",
        import_patterns=[
            r'^import\s+.+\s+from\s+["\'](.+?)["\']',
            r'^import\s+["\'](.+?)["\']',
            r'^const\s+.+\s+require\(["\'](.+?)["\']\)',
        ]
    ),
    "typescript": ParsePattern(
        function_pattern=r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>)",
        class_pattern=r"^(?:export\s+)?class\s+(\w+)",
        import_patterns=[
            r'^import\s+.+\s+from\s+["\'](.+?)["\']',
            r'^import\s+["\'](.+?)["\']',
        ]
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
        languages = ["python", "javascript", "typescript"]
        for lang in languages:
            try:
                self.parsers[lang] = get_parser(lang)
            except Exception:
                pass
    
    def _detect_language(self, file_path: Path) -> Optional[str]:
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
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
    
    def _parse_with_tree_sitter(self, source: str, file_path: str, 
                                language: str) -> tuple[list[Node], list[Edge]]:
        """Parse using tree-sitter AST."""
        parser = self.parsers.get(language)
        if not parser:
            return self._parse_with_regex(source, file_path, language)
        
        tree = parser.parse(bytes(source, "utf-8"))
        nodes = []
        edges = []
        
        def walk_node(node, depth=0):
            # Extract functions
            if node.type in ("function_definition", "function_declaration",
                           "arrow_function", "function"):
                name = self._get_node_name(node, source)
                if name:
                    node_id = f"{file_path}::{name}"
                    sig = self._extract_signature_tree_sitter(node, source)
                    content = source[node.start_byte:node.end_byte]
                    
                    nodes.append(Node(
                        id=node_id,
                        file_path=file_path,
                        name=name,
                        node_type="function",
                        start_line=node.start_point[0],
                        end_line=node.end_point[0],
                        content=content,
                        signature=sig
                    ))
            
            # Extract classes
            elif node.type in ("class_definition", "class_declaration", "class"):
                name = self._get_node_name(node, source)
                if name:
                    node_id = f"{file_path}::{name}"
                    sig = self._extract_signature_tree_sitter(node, source)
                    content = source[node.start_byte:node.end_byte]
                    
                    nodes.append(Node(
                        id=node_id,
                        file_path=file_path,
                        name=name,
                        node_type="class",
                        start_line=node.start_point[0],
                        end_line=node.end_point[0],
                        content=content,
                        signature=sig
                    ))
            
            # Extract imports
            elif node.type in ("import_statement", "import_from_statement",
                             "import_declaration"):
                imp = source[node.start_byte:node.end_byte]
                edges.append(Edge(
                    source_id=f"{file_path}::import",
                    target_id=imp.strip(),
                    edge_type="imports"
                ))
            
            # Recurse
            for child in node.children:
                walk_node(child, depth + 1)
        
        walk_node(tree.root_node)
        return nodes, edges
    
    def _get_node_name(self, node, source: str) -> Optional[str]:
        """Extract name from AST node."""
        # Try common name fields
        for field in ["name", "identifier"]:
            name_node = node.child_by_field_name(field)
            if name_node:
                return source[name_node.start_byte:name_node.end_byte]
        
        # Try first identifier child
        for child in node.children:
            if child.type == "identifier":
                return source[child.start_byte:child.end_byte]
        
        return None
    
    def _extract_signature_tree_sitter(self, node, source: str) -> str:
        """Extract signature from tree-sitter node."""
        # Get text up to the body/block
        sig_end = node.end_byte
        for child in node.children:
            if child.type in ("block", "statement_block", "class_body", 
                            "arrow_function", "function_body"):
                sig_end = child.start_byte
                break
        
        sig = source[node.start_byte:sig_end].strip()
        if sig.endswith(":"):
            sig = sig[:-1].strip()
        elif sig.endswith("=>"):
            sig = sig[:-2].strip()
        
        return sig + " ..."
    
    def _parse_with_regex(self, source: str, file_path: str, 
                          language: str) -> tuple[list[Node], list[Edge]]:
        """Fallback regex-based parsing."""
        nodes = []
        edges = []
        
        patterns = REGEX_PATTERNS.get(language)
        if not patterns:
            return [], []
        
        lines = source.split("\n")
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Check for functions
            match = re.match(patterns.function_pattern, stripped, re.MULTILINE)
            if match:
                name = match.group(1) if match.lastindex >= 1 else None
                if not name and match.lastindex >= 2:
                    name = match.group(2)
                if name:
                    node_id = f"{file_path}::{name}"
                    sig = self._extract_function_signature_regex(lines, i)
                    nodes.append(Node(
                        id=node_id,
                        file_path=file_path,
                        name=name,
                        node_type="function",
                        start_line=i,
                        end_line=self._find_block_end(lines, i),
                        content=self._extract_block(lines, i),
                        signature=sig
                    ))
            
            # Check for classes
            match = re.match(patterns.class_pattern, stripped, re.MULTILINE)
            if match:
                name = match.group(1)
                if name:
                    node_id = f"{file_path}::{name}"
                    sig = self._extract_class_signature_regex(lines, i)
                    nodes.append(Node(
                        id=node_id,
                        file_path=file_path,
                        name=name,
                        node_type="class",
                        start_line=i,
                        end_line=self._find_block_end(lines, i),
                        content=self._extract_block(lines, i),
                        signature=sig
                    ))
            
            # Check for imports
            for import_pattern in patterns.import_patterns:
                match = re.match(import_pattern, stripped)
                if match:
                    imp = match.group(1)
                    edges.append(Edge(
                        source_id=f"{file_path}::import",
                        target_id=imp,
                        edge_type="imports"
                    ))
                    break
        
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
        return "\n".join(lines[start:end + 1])

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
