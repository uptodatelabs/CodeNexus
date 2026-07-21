"""Tests for CodeNexus."""

import pytest
from pathlib import Path
import tempfile
import shutil
import os

from codenexus.graph import DependencyGraph, Node, Edge
from codenexus.parser import CodeParser

@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    dir_path = Path(tempfile.mkdtemp())
    yield dir_path
    # Force close any open connections first
    try:
        for f in dir_path.rglob("*.db"):
            try:
                os.chmod(f, 0o777)
            except:
                pass
    except:
        pass
    try:
        shutil.rmtree(dir_path, ignore_errors=True)
    except:
        pass

@pytest.fixture
def graph(temp_dir):
    """Create test graph."""
    db_path = temp_dir / "test.db"
    g = DependencyGraph(db_path)
    yield g
    g.close()

def test_graph_add_node(graph):
    """Test adding a node to the graph."""
    node = Node(
        id="test.py::func",
        file_path="test.py",
        name="func",
        node_type="function",
        start_line=1,
        end_line=5,
        content="def func(): pass",
        signature="def func(): ..."
    )
    graph.add_node(node)
    
    retrieved = graph.get_node("test.py::func")
    assert retrieved is not None
    assert retrieved.name == "func"

def test_graph_add_edge(graph):
    """Test adding an edge to the graph."""
    node1 = Node("a.py::a", "a.py", "a", "function", 1, 5, "def a(): pass", "def a(): ...")
    node2 = Node("b.py::b", "b.py", "b", "function", 1, 5, "def b(): pass", "def b(): ...")
    
    graph.add_node(node1)
    graph.add_node(node2)
    
    edge = Edge("a.py::a", "b.py::b", "calls")
    graph.add_edge(edge)
    
    dependents = graph.get_dependents("b.py::b")
    assert len(dependents) == 1

def test_graph_search(graph):
    """Test full-text search."""
    nodes = [
        Node("a.py::auth", "a.py", "auth", "function", 1, 5, "def auth(): pass", "def auth(): ..."),
        Node("b.py::login", "b.py", "login", "function", 1, 5, "def login(): pass", "def login(): ..."),
    ]
    
    for node in nodes:
        graph.add_node(node)
    
    results = graph.search_nodes("auth")
    assert len(results) >= 1

def test_parser_python(temp_dir):
    """Test Python parsing."""
    # Create test file
    test_file = temp_dir / "test.py"
    test_file.write_text("""
def hello():
    pass

class MyClass:
    def method(self):
        pass
""")
    
    parser = CodeParser()
    nodes, edges = parser.parse_file(test_file)
    
    assert len(nodes) >= 2
    assert any(n.name == "hello" for n in nodes)
    assert any(n.name == "MyClass" for n in nodes)

def test_parser_javascript(temp_dir):
    """Test JavaScript parsing."""
    test_file = temp_dir / "test.js"
    test_file.write_text("""
function hello() {
    return "world";
}

class MyClass {
    method() {
        return true;
    }
}
""")
    
    parser = CodeParser()
    nodes, edges = parser.parse_file(test_file)
    
    assert len(nodes) >= 2

def test_index_workspace(temp_dir):
    """Test workspace indexing."""
    # Create test files
    (temp_dir / "a.py").write_text("def a(): pass")
    (temp_dir / "b.py").write_text("def b(): pass")
    
    from codenexus.server import CodeNexusServer
    server = CodeNexusServer(temp_dir)
    count = server.index_workspace()
    
    assert count >= 2
    
    # Check status
    node_count = server.graph.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    assert node_count >= 2
    
    server.graph.close()
