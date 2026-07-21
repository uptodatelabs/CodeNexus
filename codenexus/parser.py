"""Regex-based code parser for common languages."""

import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from .graph import Node, Edge

@dataclass
class ParsePattern:
    """Pattern for extracting symbols."""
    function_pattern: str
    class_pattern: str
    import_patterns: list[str]

PATTERNS = {
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
    """Parse source code using regex patterns."""
    
    def __init__(self):
        self.patterns = PATTERNS
    
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
            return self._extract_symbols(source, str(file_path), language)
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return [], []
    
    def _extract_symbols(self, source: str, file_path: str, 
                         language: str) -> tuple[list[Node], list[Edge]]:
        """Extract symbols using regex patterns."""
        nodes = []
        edges = []
        
        patterns = self.patterns.get(language)
        if not patterns:
            return [], []
        
        lines = source.split("\n")
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Check for functions
            match = re.match(patterns.function_pattern, stripped, re.MULTILINE)
            if match:
                name = match.group(1) or match.group(2) if match.lastindex >= 2 else match.group(1)
                if name:
                    node_id = f"{file_path}::{name}"
                    sig = self._extract_function_signature(lines, i)
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
                    sig = self._extract_class_signature(lines, i)
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
    
    def _extract_function_signature(self, lines: list[str], start: int) -> str:
        """Extract function signature."""
        sig_lines = []
        for i in range(start, min(start + 5, len(lines))):
            sig_lines.append(lines[i].rstrip())
            if lines[i].rstrip().endswith(":"):
                break
        return " ".join(sig_lines).strip() + " ..."
    
    def _extract_class_signature(self, lines: list[str], start: int) -> str:
        """Extract class signature."""
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
