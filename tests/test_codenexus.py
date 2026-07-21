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

def test_parser_go(temp_dir):
    """Test Go parsing."""
    test_file = temp_dir / "test.go"
    test_file.write_text("""
package main

func hello() {
    return
}

func (s *Server) Start() error {
    return nil
}

type User struct {
    Name string
}
""")
    
    parser = CodeParser(use_tree_sitter=False)
    nodes, edges = parser.parse_file(test_file)
    
    assert len(nodes) >= 2
    assert any(n.name == "hello" for n in nodes)
    assert any(n.name == "Start" for n in nodes)

def test_parser_rust(temp_dir):
    """Test Rust parsing."""
    test_file = temp_dir / "test.rs"
    test_file.write_text("""
fn hello() {
    return;
}

pub fn calculate(x: i32) -> i32 {
    x + 1
}

struct User {
    name: String,
}

enum Color {
    Red,
    Green,
    Blue,
}
""")
    
    parser = CodeParser(use_tree_sitter=False)
    nodes, edges = parser.parse_file(test_file)
    
    assert len(nodes) >= 3
    assert any(n.name == "hello" for n in nodes)
    assert any(n.name == "calculate" for n in nodes)
    assert any(n.name == "User" for n in nodes)

def test_parser_java(temp_dir):
    """Test Java parsing."""
    test_file = temp_dir / "test.java"
    test_file.write_text("""
public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }
    
    private void helper() {
        // helper method
    }
}
""")
    
    parser = CodeParser(use_tree_sitter=False)
    nodes, edges = parser.parse_file(test_file)
    
    assert len(nodes) >= 2
    assert any(n.name == "Calculator" for n in nodes)
    assert any(n.name == "add" for n in nodes)

def test_parser_csharp(temp_dir):
    """Test C# parsing."""
    test_file = temp_dir / "test.cs"
    test_file.write_text("""
using System;

namespace MyApp
{
    public class Program
    {
        public static void Main(string[] args)
        {
            Console.WriteLine("Hello");
        }
        
        private int Calculate(int x)
        {
            return x * 2;
        }
    }
}
""")
    
    parser = CodeParser(use_tree_sitter=False)
    nodes, edges = parser.parse_file(test_file)
    
    assert len(nodes) >= 2
    assert any(n.name == "Program" for n in nodes)
    assert any(n.name == "Main" for n in nodes)

def test_pagerank(graph):
    """Test PageRank centrality computation."""
    # Create nodes
    nodes = [
        Node("a.py::main", "a.py", "main", "function", 1, 10, "def main(): pass", "def main(): ..."),
        Node("b.py::helper", "b.py", "helper", "function", 1, 5, "def helper(): pass", "def helper(): ..."),
        Node("c.py::utils", "c.py", "utils", "function", 1, 5, "def utils(): pass", "def utils(): ..."),
        Node("d.py::config", "d.py", "config", "function", 1, 3, "def config(): pass", "def config(): ..."),
    ]
    
    for node in nodes:
        graph.add_node(node)
    
    # Create edges (main -> helper, main -> utils, helper -> config, utils -> config)
    edges = [
        Edge("a.py::main", "b.py::helper", "calls"),
        Edge("a.py::main", "c.py::utils", "calls"),
        Edge("b.py::helper", "d.py::config", "calls"),
        Edge("c.py::utils", "d.py::config", "calls"),
    ]
    
    for edge in edges:
        graph.add_edge(edge)
    
    # Compute PageRank
    scores = graph.compute_pagerank()
    
    # config should have highest score (most incoming links)
    assert scores["d.py::config"] > scores["a.py::main"]
    assert scores["d.py::config"] > scores["b.py::helper"]
    
    # Get top central nodes
    top_nodes = graph.get_top_central_nodes(2)
    assert len(top_nodes) == 2
    assert top_nodes[0].name == "config"

def test_impact_graph(graph):
    """Test impact graph generation."""
    # Create nodes
    nodes = [
        Node("a.py::main", "a.py", "main", "function", 1, 10, "def main(): pass", "def main(): ..."),
        Node("b.py::helper", "b.py", "helper", "function", 1, 5, "def helper(): pass", "def helper(): ..."),
        Node("c.py::utils", "c.py", "utils", "function", 1, 5, "def utils(): pass", "def utils(): ..."),
        Node("d.py::caller", "d.py", "caller", "function", 1, 5, "def caller(): pass", "def caller(): ..."),
    ]
    
    for node in nodes:
        graph.add_node(node)
    
    # Create edges: caller -> main -> helper -> utils
    edges = [
        Edge("d.py::caller", "a.py::main", "calls"),  # caller calls main
        Edge("a.py::main", "b.py::helper", "calls"),  # main calls helper
        Edge("b.py::helper", "c.py::utils", "calls"),  # helper calls utils
    ]
    
    for edge in edges:
        graph.add_edge(edge)
    
    # Get impact graph for main (who depends on main?)
    impact = graph.get_impact_graph("a.py::main", depth=2)
    
    # caller depends on main
    assert impact["total"] >= 1
    assert len(impact["direct"]) >= 1
    assert impact["direct"][0]["name"] == "caller"
