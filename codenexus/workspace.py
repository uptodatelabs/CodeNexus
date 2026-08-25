"""Multi-repo workspace support for CodeNexus."""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from .graph import DependencyGraph
from .parser import CodeParser, detect_language
from .resolver import FileEntry, ImportResolver
from .server import SKIP_DIRS, SOURCE_EXTENSIONS

logger = logging.getLogger(__name__)

_ALIAS_RE = re.compile(r"^[\w][\w.-]*$")


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
        # False when an existing config file failed to load: saving would then
        # wipe every registered repo, so writes are refused until the user
        # fixes or removes the corrupt file.
        self._config_load_ok = False
        self.graphs: dict[str, DependencyGraph] = {}
        self.parser = CodeParser()

        self._load_config()

    def _load_config(self):
        """Load workspace configuration."""
        if not self.config_path.exists():
            self._config_load_ok = True
            return
        try:
            with open(self.config_path, encoding="utf-8-sig") as f:
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
            self._config_load_ok = True
        except Exception as e:
            # Leave self.config None and refuse future saves rather than
            # silently replacing the registry with a fresh default.
            logger.error(
                "Could not load workspace config %s (%s); refusing to overwrite it. "
                "Fix or delete the file to start a new workspace.",
                self.config_path,
                e,
            )

    def save_config(self) -> bool:
        """Save workspace configuration."""
        if not self.config:
            return False

        if not self._config_load_ok:
            logger.error(
                "Refusing to save workspace config: the existing file could not "
                "be loaded earlier, saving would destroy registered repos."
            )
            return False

        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "name": self.config.name,
            "repos": [
                {"alias": r.alias, "path": str(r.path), "description": r.description}
                for r in self.config.repos
            ],
        }

        tmp_path = self.config_path.with_suffix(".json.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            tmp_path.replace(self.config_path)
            return True
        except OSError as e:
            logger.error("Could not save workspace config: %s", e)
            return False


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
            if not self._config_load_ok:
                logger.error("Workspace config is corrupt; fix or remove %s first.", self.config_path)
                return False
            self.config = WorkspaceConfig(name="default")

        alias = alias.strip()
        if not _ALIAS_RE.match(alias):
            logger.error(
                "Invalid alias '%s': use letters, digits, dots, dashes and "
                "underscores only (no path separators).",
                alias,
            )
            return False

        # Check if alias already exists
        for repo in self.config.repos:
            if repo.alias == alias:
                logger.warning("Repository '%s' already exists", alias)
                return False

        # Check if path exists
        if not path.exists():
            logger.error("Path does not exist: %s", path)
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
                db_path = None
                if alias in self.graphs:
                    db_path = self.graphs[alias].db_path
                    self.graphs[alias].close()
                    del self.graphs[alias]

                # Remove the repo's derived index data so re-adding the alias
                # later doesn't resurrect stale nodes.
                if db_path is None:
                    db_path = self._get_repo_db_path(alias)
                try:
                    db_path.unlink(missing_ok=True)
                except OSError as e:
                    logger.warning("Could not remove index file %s: %s", db_path, e)

                return True

        logger.warning("Repository '%s' not found", alias)
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

        # Re-indexing rebuilds the repo from scratch: stale nodes/edges from
        # deleted or renamed files must not accumulate.
        graph.clear()

        # Get source files
        source_files = []
        for file_path in repo_config.path.rglob("*"):
            if file_path.suffix.lower() not in SOURCE_EXTENSIONS:
                continue
            if any(part in SKIP_DIRS for part in file_path.parts):
                continue
            source_files.append(file_path)

        # Parse and index
        entries: list[FileEntry] = []
        indexed = 0
        for file_path in source_files:
            try:
                nodes, edges = self.parser.parse_file(file_path)

                # Adjust file paths to be relative to repo
                rel_path = file_path.relative_to(repo_config.path)
                rel_posix = rel_path.as_posix()

                symbols: dict[str, str] = {}
                for node in nodes:
                    # Update file path to include repo alias
                    node.file_path = f"{alias}/{rel_posix}"
                    node.id = f"{alias}:{node.id}"
                    symbols.setdefault(node.name, node.id)
                graph.add_nodes(nodes)

                raw_imports = [edge.target_id for edge in edges]
                # Raw ::import edges never connect real nodes; the resolver
                # rewrites them into module/symbol edges below.
                entries.append(
                    FileEntry(
                        abs_path=file_path,
                        rel_path=f"{alias}/{rel_posix}",
                        language=detect_language(file_path) or "",
                        symbols=symbols,
                        raw_imports=raw_imports,
                    )
                )
                indexed += 1
            except Exception as e:
                logger.warning("Error indexing %s: %s", file_path, e)

        # Rewrite imports into real module/symbol edges.
        if entries:
            resolver = ImportResolver(repo_config.path)
            module_nodes, import_edges = resolver.build(entries)
            for node in module_nodes:
                node.id = f"{alias}:{node.id}"
                node.file_path = f"{alias}/{node.file_path}"
            for edge in import_edges:
                edge.source_id = f"{alias}:{edge.source_id}"
                edge.target_id = f"{alias}:{edge.target_id}"
            graph.add_nodes(module_nodes)
            graph.add_edges(import_edges)

        # Compute centrality
        if indexed > 0:
            graph.compute_pagerank()

        return indexed

    def _open_existing_graph(self, alias: str) -> DependencyGraph | None:
        """Open a repo graph only when its database already exists."""
        if alias not in self.graphs:
            db_path = self._get_repo_db_path(alias)
            if not db_path.exists():
                return None
            self.graphs[alias] = DependencyGraph(db_path)
        return self.graphs[alias]

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
            logger.info("Indexing %s...", repo.alias)
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
            # Lazily open every registered repo: after a restart, previously
            # indexed repos used to silently vanish from results.
            graph = self._open_existing_graph(alias)
            if graph is None:
                continue

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
            graph = self._open_existing_graph(repo.alias)
            if graph is None:
                continue

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
            # Read-only status must not materialize empty .db files for
            # repos that were registered but never indexed.
            graph = self._open_existing_graph(repo.alias)
            node_count = 0
            if graph is not None:
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
