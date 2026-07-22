"""Multi-repo workspace support for CodeNexus."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from .graph import DependencyGraph
from .parser import CodeParser


@dataclass
class RepoConfig:
    """Repository configuration."""

    alias: str
    path: Path
    description: str = ""


@dataclass
class WorkspaceConfig:
    """Workspace configuration."""

    name: str
    repos: list[RepoConfig] = field(default_factory=list)


class MultiRepoWorkspace:
    """Manage multiple repositories as a unified workspace."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.config_path = workspace_path / ".codenexus" / "workspace.json"
        self.config: WorkspaceConfig | None = None
        self.graphs: dict[str, DependencyGraph] = {}
        self.parser = CodeParser()

        self._load_config()

    def _load_config(self):
        """Load workspace configuration."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                    self.config = WorkspaceConfig(
                        name=data.get("name", "default"),
                        repos=[
                            RepoConfig(
                                alias=r["alias"],
                                path=Path(r["path"]),
                                description=r.get("description", ""),
                            )
                            for r in data.get("repos", [])
                        ],
                    )
            except Exception as e:
                print(f"Error loading workspace config: {e}")

    def save_config(self):
        """Save workspace configuration."""
        if not self.config:
            return

        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "name": self.config.name,
            "repos": [
                {"alias": r.alias, "path": str(r.path), "description": r.description}
                for r in self.config.repos
            ],
        }

        with open(self.config_path, "w") as f:
            json.dump(data, f, indent=2)

    def add_repo(self, alias: str, path: Path, description: str = "") -> bool:
        """
        Add a repository to the workspace.

        Args:
            alias: Short name for the repo
            path: Path to the repository
            description: Optional description

        Returns:
            True if added successfully
        """
        if not self.config:
            self.config = WorkspaceConfig(name="default")

        # Check if alias already exists
        for repo in self.config.repos:
            if repo.alias == alias:
                print(f"Repository '{alias}' already exists")
                return False

        # Check if path exists
        if not path.exists():
            print(f"Path does not exist: {path}")
            return False

        self.config.repos.append(
            RepoConfig(alias=alias, path=path.absolute(), description=description)
        )

        self.save_config()
        return True

    def remove_repo(self, alias: str) -> bool:
        """
        Remove a repository from the workspace.

        Args:
            alias: Repository alias to remove

        Returns:
            True if removed successfully
        """
        if not self.config:
            return False

        for i, repo in enumerate(self.config.repos):
            if repo.alias == alias:
                self.config.repos.pop(i)
                self.save_config()

                # Close graph if open
                if alias in self.graphs:
                    self.graphs[alias].close()
                    del self.graphs[alias]

                return True

        print(f"Repository '{alias}' not found")
        return False

    def _get_repo_db_path(self, alias: str) -> Path:
        """Get database path for a repository."""
        return self.workspace_path / ".codenexus" / "repos" / f"{alias}.db"

    def _get_repo_graph(self, alias: str) -> DependencyGraph:
        """Get or create graph for a repository."""
        if alias not in self.graphs:
            db_path = self._get_repo_db_path(alias)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.graphs[alias] = DependencyGraph(db_path)
        return self.graphs[alias]

    def index_repo(self, alias: str) -> int:
        """
        Index a single repository.

        Args:
            alias: Repository alias

        Returns:
            Number of files indexed
        """
        if not self.config:
            print("No workspace configuration")
            return 0

        repo_config = None
        for repo in self.config.repos:
            if repo.alias == alias:
                repo_config = repo
                break

        if not repo_config:
            print(f"Repository '{alias}' not found")
            return 0

        graph = self._get_repo_graph(alias)

        # Get source files
        extensions = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".cs"}
        skip_dirs = {
            "node_modules",
            ".git",
            "__pycache__",
            "venv",
            ".venv",
            "dist",
            "build",
            ".codenexus",
        }

        source_files = []
        for ext in extensions:
            for file_path in repo_config.path.rglob(f"*{ext}"):
                if not any(skip in file_path.parts for skip in skip_dirs):
                    source_files.append(file_path)

        # Parse and index
        indexed = 0
        for file_path in source_files:
            try:
                nodes, edges = self.parser.parse_file(file_path)

                # Adjust file paths to be relative to repo
                rel_path = file_path.relative_to(repo_config.path)

                for node in nodes:
                    # Update file path to include repo alias
                    node.file_path = f"{alias}/{rel_path}"
                    node.id = f"{alias}:{node.id}"
                    graph.add_node(node)

                for edge in edges:
                    edge.source_id = f"{alias}:{edge.source_id}"
                    graph.add_edge(edge)

                indexed += 1
            except Exception as e:
                print(f"Error indexing {file_path}: {e}")

        # Compute centrality
        if indexed > 0:
            graph.compute_pagerank()

        return indexed

    def index_all(self) -> dict[str, int]:
        """
        Index all repositories in the workspace.

        Returns:
            Dictionary mapping repo alias to file count
        """
        results = {}

        if not self.config:
            return results

        for repo in self.config.repos:
            print(f"Indexing {repo.alias}...")
            results[repo.alias] = self.index_repo(repo.alias)

        return results

    def search(self, query: str, repos: list[str] | None = None, limit: int = 10) -> list[dict]:
        """
        Search across repositories.

        Args:
            query: Search query
            repos: List of repo aliases to search (None = all)
            limit: Max results per repo

        Returns:
            List of search results with repo info
        """
        results = []

        if not self.config:
            return results

        target_repos = repos or [r.alias for r in self.config.repos]

        for alias in target_repos:
            if alias not in self.graphs:
                continue

            graph = self.graphs[alias]
            nodes = graph.search_nodes(query, limit=limit)

            for node in nodes:
                results.append({"repo": alias, "node": node, "score": node.centrality_score})

        # Sort by score
        results.sort(key=lambda x: x["score"], reverse=True)

        return results

    def get_cross_repo_dependencies(self) -> dict[str, list[str]]:
        """
        Detect dependencies between repositories.

        Returns:
            Dictionary mapping repo to list of dependent repos
        """
        dependencies: dict[str, set] = {
            r.alias: set() for r in (self.config.repos if self.config else [])
        }

        if not self.config:
            return dependencies

        # Simple heuristic: check for import patterns
        for repo in self.config.repos:
            graph = self._get_repo_graph(repo.alias)

            # Get all imports
            rows = graph.conn.execute("""
                SELECT content FROM nodes WHERE node_type = 'import'
            """).fetchall()

            for row in rows:
                import_content = row[0].lower()

                # Check other repos
                for other_repo in self.config.repos:
                    if other_repo.alias != repo.alias:
                        if other_repo.alias.lower() in import_content:
                            dependencies[repo.alias].add(other_repo.alias)

        return {k: list(v) for k, v in dependencies.items()}

    def get_impact_analysis(self, repo: str, node_id: str, depth: int = 2) -> dict:
        """
        Analyze impact across repositories.

        Args:
            repo: Repository alias
            node_id: Node ID to analyze
            depth: Depth of analysis

        Returns:
            Impact analysis results
        """
        if repo not in self.graphs:
            return {"error": f"Repository '{repo}' not indexed"}

        graph = self.graphs[repo]
        impact = graph.get_impact_graph(node_id, depth=depth)

        # Cross-repo impact
        cross_repo_impact = []
        deps = self.get_cross_repo_dependencies()

        if repo in deps:
            for dep_repo in deps[repo]:
                if dep_repo in self.graphs:
                    dep_graph = self.graphs[dep_repo]
                    # Search for related nodes in dependent repos
                    node = graph.get_node(node_id)
                    if node:
                        related = dep_graph.search_nodes(node.name, limit=5)
                        for rel in related:
                            cross_repo_impact.append(
                                {"repo": dep_repo, "node": rel.name, "file": rel.file_path}
                            )

        impact["cross_repo"] = cross_repo_impact
        impact["total"] += len(cross_repo_impact)

        return impact

    def get_status(self) -> dict:
        """Get workspace status."""
        if not self.config:
            return {"name": "none", "repos": 0}

        repo_status = []
        for repo in self.config.repos:
            graph = self._get_repo_graph(repo.alias)
            node_count = graph.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]

            repo_status.append({"alias": repo.alias, "path": str(repo.path), "nodes": node_count})

        return {
            "name": self.config.name,
            "repos": len(self.config.repos),
            "repo_status": repo_status,
        }

    def close(self):
        """Close all graph connections."""
        for graph in self.graphs.values():
            graph.close()
        self.graphs.clear()
