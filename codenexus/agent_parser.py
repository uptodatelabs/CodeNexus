"""Agent config parsers for detecting indexed projects."""

import json
from pathlib import Path


class AgentConfigParser:
    """Base class for agent config parsers."""

    def __init__(self):
        self.config_paths: list[Path] = []

    def find_config(self) -> Path | None:
        """Find the config file."""
        for path in self.config_paths:
            if path.exists():
                return path
        return None

    def parse(self, config_path: Path) -> dict:
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

class ClaudeCodeParser(AgentConfigParser):
    """Parse Claude Code settings."""

    def __init__(self):
        super().__init__()
        self.config_paths = [
            Path.home() / '.claude.json',
            Path('.mcp.json'),
            Path('.claude') / 'settings.json',
        ]

    def parse(self, config_path: Path) -> list[dict]:
        projects = []

        try:
            with open(config_path) as f:
                data = json.load(f)

            # Check for mcpServers in various locations
            mcp_servers = {}

            # From .claude.json
            if 'mcpServers' in data:
                mcp_servers.update(data['mcpServers'])

            # From projects
            if 'projects' in data:
                for project_path, project_data in data['projects'].items():
                    if 'mcpServers' in project_data:
                        for name, config in project_data['mcpServers'].items():
                            if name == 'codenexus':
                                projects.append({
                                    'path': project_path,
                                    'config': config
                                })

            # From mcpServers directly
            for name, config in mcp_servers.items():
                if name == 'codenexus':
                    # Extract project path from args
                    args = config.get('args', [])
                    project_path = None
                    for i, arg in enumerate(args):
                        if arg == '-w' and i + 1 < len(args):
                            project_path = args[i + 1]
                            break

                    if project_path:
                        projects.append({
                            'path': project_path,
                            'config': config
                        })

        except (json.JSONDecodeError, FileNotFoundError):
            pass

        return projects

class HermesParser(AgentConfigParser):
    """Parse Hermes config.yaml."""

    def __init__(self):
        super().__init__()
        self.config_paths = [
            Path.home() / '.hermes' / 'config.yaml',
            Path.home() / '.hermes' / 'config.json',
        ]

    def parse(self, config_path: Path) -> list[dict]:
        projects = []

        try:
            if config_path.suffix == '.yaml':
                import yaml
                with open(config_path) as f:
                    data = yaml.safe_load(f) or {}
            else:
                with open(config_path) as f:
                    data = json.load(f)

            # Check for mcp_servers
            mcp_servers = data.get('mcp_servers', {})

            for name, config in mcp_servers.items():
                if name == 'codenexus':
                    args = config.get('args', [])
                    project_path = None
                    for i, arg in enumerate(args):
                        if arg == '-w' and i + 1 < len(args):
                            project_path = args[i + 1]
                            break

                    if project_path:
                        projects.append({
                            'path': project_path,
                            'config': config
                        })

        except (json.JSONDecodeError, yaml.YAMLError, FileNotFoundError):
            pass

        return projects

class CursorParser(AgentConfigParser):
    """Parse Cursor mcp.json."""

    def __init__(self):
        super().__init__()
        self.config_paths = [
            Path.home() / '.cursor' / 'mcp.json',
            Path('.cursor') / 'mcp.json',
        ]

    def parse(self, config_path: Path) -> list[dict]:
        projects = []

        try:
            with open(config_path) as f:
                data = json.load(f)

            mcp_servers = data.get('mcpServers', {})

            for name, config in mcp_servers.items():
                if name == 'codenexus':
                    args = config.get('args', [])
                    project_path = None
                    for i, arg in enumerate(args):
                        if arg == '-w' and i + 1 < len(args):
                            project_path = args[i + 1]
                            break

                    if project_path:
                        projects.append({
                            'path': project_path,
                            'config': config
                        })

        except (json.JSONDecodeError, FileNotFoundError):
            pass

        return projects

class CodexParser(AgentConfigParser):
    """Parse Codex config.toml."""

    def __init__(self):
        super().__init__()
        self.config_paths = [
            Path.home() / '.codex' / 'config.toml',
        ]

    def parse(self, config_path: Path) -> list[dict]:
        projects = []

        try:
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib

            with open(config_path, 'rb') as f:
                data = tomllib.load(f)

            mcp_servers = data.get('mcp_servers', {})

            for name, config in mcp_servers.items():
                if name == 'codenexus':
                    args = config.get('args', [])
                    project_path = None
                    for i, arg in enumerate(args):
                        if arg == '-w' and i + 1 < len(args):
                            project_path = args[i + 1]
                            break

                    if project_path:
                        projects.append({
                            'path': project_path,
                            'config': config
                        })

        except Exception:
            pass

        return projects

def get_all_indexed_projects() -> dict[str, list[dict]]:
    """Get indexed projects from all detected agents."""
    parsers = {
        'Claude Code': ClaudeCodeParser(),
        'Hermes': HermesParser(),
        'Cursor': CursorParser(),
        'Codex': CodexParser(),
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
    index_path = path / '.codenexus' / 'index.db'

    if index_path.exists():
        return index_path

    return None
