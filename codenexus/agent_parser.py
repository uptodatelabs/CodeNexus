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

class OpenClawParser(AgentConfigParser):
    """Parse OpenClaw skill definition (SKILL.md) for codenexus paths."""

    def __init__(self):
        super().__init__()
        # Mirror wizard._find_openclaw_skills_path() lookup
        self.config_paths = [
            Path.home() / '.openclaw' / 'workspace' / 'skills' / 'codenexus' / 'SKILL.md',
            Path.home() / '.config' / 'openclaw' / 'workspace' / 'skills' / 'codenexus' / 'SKILL.md',
            Path.home() / '.openclaw' / 'skills' / 'codenexus' / 'SKILL.md',
        ]

    def parse(self, config_path: Path) -> list[dict]:
        projects = []
        try:
            text = config_path.read_text()
        except Exception:
            return projects

        # Match: codenexus ... -w <path> ...  (index or serve)
        import re
        for m in re.finditer(r'codenexus\b[^\n]*?-w\s+(\S+)', text):
            raw = m.group(1).strip()
            # Drop surrounding backticks/quotes if present
            project_path = raw.strip('`"')
            if project_path and project_path not in [p['path'] for p in projects]:
                projects.append({
                    'path': project_path,
                    'config': {'command': 'codenexus', 'args': ['-w', project_path, 'serve']}
                })
        return projects

class OpenCodeParser(AgentConfigParser):
    """Parse OpenCode opencode.jsonc (JSON5) for codenexus MCP server.

    OpenCode stores MCP servers under the ``mcp`` key (not ``mcpServers``)
    and writes the config to ``~/.config/opencode/opencode.jsonc`` (XDG dir).
    Example entry::

        {
          "mcp": {
            "codenexus": {"type": "local", "command": ["codenexus", "-w", "/p", "serve"]}
          }
        }
    """

    def __init__(self):
        super().__init__()
        self.config_paths = [
            Path.home() / '.config' / 'opencode' / 'opencode.jsonc',
            Path.home() / '.opencode' / 'opencode.jsonc',
            Path.home() / '.config' / 'opencode' / 'config.json',
        ]

    def parse(self, config_path: Path) -> list[dict]:
        projects = []
        try:
            # Reuse wizard's JSON5-safe loader (no external dependency).
            from .wizard import _load_jsonc
            data = _load_jsonc(config_path)
        except Exception:
            return projects

        # OpenCode nests servers under `mcp`, not `mcpServers`.
        mcp_servers = data.get('mcp', {})
        for name, config in mcp_servers.items():
            if name != 'codenexus' or not isinstance(config, dict):
                continue
            # `command` may be a string or a list.
            raw_cmd = config.get('command', [])
            args = raw_cmd if isinstance(raw_cmd, list) else [raw_cmd]
            project_path = None
            for i, arg in enumerate(args):
                if arg == '-w' and i + 1 < len(args):
                    project_path = args[i + 1]
                    break
            if project_path:
                projects.append({'path': project_path, 'config': config})
        return projects

class AntigravityParser(AgentConfigParser):
    """Parse Antigravity mcp_config.json for codenexus MCP server."""

    def __init__(self):
        super().__init__()
        self.config_paths = [
            Path.home() / '.gemini' / 'config' / 'mcp_config.json',
            Path('.agents') / 'mcp_config.json',
        ]

    def parse(self, config_path: Path) -> list[dict]:
        projects = []
        try:
            with open(config_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, OSError):
            return projects

        mcp_servers = data.get('mcpServers', {})
        for name, config in mcp_servers.items():
            if name != 'codenexus':
                continue
            args = config.get('args', []) if isinstance(config, dict) else []
            project_path = None
            for i, arg in enumerate(args):
                if arg == '-w' and i + 1 < len(args):
                    project_path = args[i + 1]
                    break
            if project_path:
                projects.append({'path': project_path, 'config': config})
        return projects

def get_all_indexed_projects() -> dict[str, list[dict]]:
    """Get indexed projects from all detected agents."""
    parsers = {
        'Claude Code': ClaudeCodeParser(),
        'Hermes': HermesParser(),
        'Cursor': CursorParser(),
        'Codex': CodexParser(),
        'OpenClaw': OpenClawParser(),
        'OpenCode': OpenCodeParser(),
        'Antigravity': AntigravityParser(),
    }

    results = {}
    for agent_name, parser in parsers.items():
        projects = parser.get_indexed_projects()
        if projects:
            results[agent_name] = projects

    return results

def find_codenexus_index(project_path: str) -> Path | None:
    """Find the CodeNexus index (.codenexus/index.db) for a project path.

    Handles two real-world cases where the agent config's ``-w`` path does
    not exactly match the index root:

    1. The path itself is the index root (``<path>/.codenexus/index.db``).
    2. The path is an *ancestor* of the index root (e.g. config points at
       ``/home/user`` but the index lives in ``/home/user/project/.codenexus``):
       walk *down* one level to find the nearest index.

    Deliberately does NOT walk *up* past the given path: doing so would reach
    unrelated parent directories (e.g. the real user HOME) and match the wrong
    index. Returns the ``index.db`` path, or ``None`` if no index is found.
    """
    path = Path(project_path).resolve()

    # Case 1: exact index root.
    direct = path / ".codenexus" / "index.db"
    if direct.exists():
        return direct

    # Case 2: path is an ancestor of the index root — walk down one level.
    # Only descend a single level to avoid scanning huge trees unexpectedly.
    for sub in sorted(path.iterdir()) if path.is_dir() else []:
        if sub.is_dir():
            candidate = sub / ".codenexus" / "index.db"
            if candidate.exists():
                return candidate

    return None
