"""Agent config parsers for detecting indexed projects."""

import json
from pathlib import Path

# PyYAML is a hard dependency of this package, so importing it at module
# scope is safe (referencing yaml.YAMLError from a lazy import inside try
# blocks used to raise NameError when handling unrelated failures).
import yaml


class AgentConfigParser:
    """Base class for agent config parsers."""

    def __init__(self):
        # Ordered by precedence: the first existing file wins.
        self.config_paths: list[Path] = []

    def find_config(self) -> Path | None:
        """Find the config file."""
        for path in self.config_paths:
            if path.exists():
                return path
        return None

    def parse(self, config_path: Path) -> list[dict]:
        """Parse config file and return indexed projects."""
        raise NotImplementedError

    def get_indexed_projects(self) -> list[dict]:
        """Get list of indexed projects."""
        config_path = self.find_config()
        if not config_path:
            return []

        try:
            return self.parse(config_path)
        except Exception as e:
            print(f"Error parsing {config_path}: {e}")
            return []

    @staticmethod
    def _extract_project_from_args(args: list) -> str | None:
        """Pull the -w/--workspace project path out of an MCP server argv.

        Tilde paths are expanded and only existing directories are reported:
        garbled or stale entries would otherwise surface as deletable
        "projects" in wizard clear.
        """
        for i, arg in enumerate(args):
            if arg in ("-w", "--workspace") and i + 1 < len(args):
                expanded = str(Path(args[i + 1]).expanduser())
                if Path(expanded).is_dir():
                    return expanded
                return None
        return None


class ClaudeCodeParser(AgentConfigParser):
    """Parse Claude Code settings.

    The global ~/.claude.json is checked FIRST: local .mcp.json files shadow
    it otherwise, hiding globally-registered projects from wizard clear.
    """

    def __init__(self):
        super().__init__()
        self.config_paths = [
            Path.home() / ".claude.json",
            Path(".mcp.json"),
            Path(".claude") / "settings.json",
        ]

    def parse(self, config_path: Path) -> list[dict]:
        projects = []

        with open(config_path, encoding="utf-8-sig") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return projects

        # Per-project MCP servers (the recommended multi-project layout)
        projects_section = data.get("projects")
        if isinstance(projects_section, dict):
            for project_path, project_data in projects_section.items():
                if not isinstance(project_data, dict):
                    continue
                servers = project_data.get("mcpServers")
                if not isinstance(servers, dict):
                    continue
                if "codenexus" in servers:
                    projects.append({"path": str(project_path), "config": servers["codenexus"]})

        # Globally registered server with -w <project>
        mcp_servers = data.get("mcpServers")
        if isinstance(mcp_servers, dict) and "codenexus" in mcp_servers:
            config = mcp_servers["codenexus"]
            extracted = self._extract_project_from_args(config.get("args", []) if isinstance(config, dict) else [])
            if extracted:
                projects.append({"path": extracted, "config": config})

        return projects


class HermesParser(AgentConfigParser):
    """Parse Hermes config.yaml / config.json."""

    def __init__(self):
        super().__init__()
        self.config_paths = [
            Path.home() / ".hermes" / "config.yaml",
            Path.home() / ".hermes" / "config.json",
        ]

    def parse(self, config_path: Path) -> list[dict]:
        projects = []

        if config_path.suffix == ".yaml":
            with open(config_path, encoding="utf-8-sig") as f:
                data = yaml.safe_load(f) or {}
        else:
            with open(config_path, encoding="utf-8-sig") as f:
                data = json.load(f)

        mcp_servers = data.get("mcp_servers", {})
        for name, config in (mcp_servers or {}).items():
            if name == "codenexus":
                args = config.get("args", []) if isinstance(config, dict) else []
                extracted = self._extract_project_from_args(args)
                if extracted:
                    projects.append({"path": extracted, "config": config})

        return projects


class CursorParser(AgentConfigParser):
    """Parse Cursor mcp.json."""

    def __init__(self):
        super().__init__()
        self.config_paths = [
            Path.home() / ".cursor" / "mcp.json",
            Path(".cursor") / "mcp.json",
        ]

    def parse(self, config_path: Path) -> list[dict]:
        projects = []

        with open(config_path, encoding="utf-8-sig") as f:
            data = json.load(f)

        mcp_servers = data.get("mcpServers", {})
        for name, config in (mcp_servers or {}).items():
            if name == "codenexus":
                args = config.get("args", []) if isinstance(config, dict) else []
                extracted = self._extract_project_from_args(args)
                if extracted:
                    projects.append({"path": extracted, "config": config})

        return projects


class CodexParser(AgentConfigParser):
    """Parse Codex config.toml."""

    def __init__(self):
        super().__init__()
        self.config_paths = [
            Path.home() / ".codex" / "config.toml",
        ]

    def parse(self, config_path: Path) -> list[dict]:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib

        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        projects = []
        mcp_servers = data.get("mcp_servers", {})
        for name, config in (mcp_servers or {}).items():
            if name == "codenexus":
                args = config.get("args", []) if isinstance(config, dict) else []
                extracted = self._extract_project_from_args(args)
                if extracted:
                    projects.append({"path": extracted, "config": config})

        return projects


def get_all_indexed_projects() -> dict[str, list[dict]]:
    """Get indexed projects from all detected agents."""
    parsers = {
        "Claude Code": ClaudeCodeParser(),
        "Hermes": HermesParser(),
        "Cursor": CursorParser(),
        "Codex": CodexParser(),
    }

    results = {}
    for agent_name, parser in parsers.items():
        projects = parser.get_indexed_projects()
        if projects:
            results[agent_name] = projects

    return results


def find_codenexus_index(project_path: str) -> Path | None:
    """Find CodeNexus index for a project."""
    path = Path(project_path)
    index_path = path / ".codenexus" / "index.db"

    if index_path.exists():
        return index_path

    return None
