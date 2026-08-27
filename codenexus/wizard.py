"""Setup wizard for AI coding agent integration."""

import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


def _load_jsonc(config_path: Path) -> dict:
    """Parse a JSONC/JSON5 file (comments allowed) without external deps.

    Handles ``//`` line comments and ``/* */`` block comments, which
    OpenCode's ``opencode.jsonc`` may contain. Falls back to strict JSON
    if the comment stripping is unsafe.
    """
    try:
        text = config_path.read_text()
    except OSError:
        return {}

    import re

    # Strip block comments first.
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

    # Strip // line comments (not inside strings).
    def _strip_line_comments(src: str) -> str:
        out = []
        in_string = False
        escape = False
        i = 0
        n = len(src)
        while i < n:
            ch = src[i]
            if escape:
                out.append(ch)
                escape = False
                i += 1
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                i += 1
                continue
            if ch == '"':
                in_string = not in_string
                out.append(ch)
                i += 1
                continue
            if not in_string and ch == "/" and i + 1 < n and src[i + 1] == "/":
                # Skip to end of line (or end of text).
                while i < n and src[i] != "\n":
                    i += 1
                # Keep the newline if present.
                if i < n:
                    out.append("\n")
                    i += 1
                continue
            out.append(ch)
            i += 1
        return "".join(out)

    cleaned = _strip_line_comments(text)

    try:
        return json.loads(cleaned) or {}
    except json.JSONDecodeError:
        # Trailing commas are valid JSON5 but not strict JSON; strip them.
        try:
            cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
            return json.loads(cleaned) or {}
        except json.JSONDecodeError:
            return {}


class AgentType(Enum):
    CLAUDE_CODE = "claude_code"
    OPENCLAW = "openclaw"
    HERMES = "hermes"
    CURSOR = "cursor"
    WINDSURF = "windsurf"
    COPILOT = "copilot"
    CODEX = "codex"
    ZED = "zed"
    CONTINUE = "continue"
    AUGMENT = "augment"
    OPENCODE = "opencode"
    ANTIGRAVITY = "antigravity"


@dataclass
class AgentInfo:
    name: str
    agent_type: AgentType
    config_file: str
    mcp_support: bool
    cli_command: str
    description: str


AGENTS = {
    AgentType.CLAUDE_CODE: AgentInfo(
        name="Claude Code",
        agent_type=AgentType.CLAUDE_CODE,
        config_file="~/.claude.json",
        mcp_support=True,
        cli_command="claude mcp add",
        description="Anthropic Claude Code - Best for complex coding tasks"
    ),
    AgentType.OPENCLAW: AgentInfo(
        name="OpenClaw",
        agent_type=AgentType.OPENCLAW,
        config_file="~/.openclaw/workspace/skills/codenexus/SKILL.md",
        mcp_support=True,
        cli_command="openclaw skill add",
        description="Personal AI assistant with messaging integration",
    ),
    AgentType.HERMES: AgentInfo(
        name="Hermes Agent",
        agent_type=AgentType.HERMES,
        config_file="~/.hermes/config.yaml",
        mcp_support=True,
        cli_command="hermes mcp add",
        description="Self-improving AI agent by Nous Research",
    ),
    AgentType.CURSOR: AgentInfo(
        name="Cursor",
        agent_type=AgentType.CURSOR,
        config_file="~/.cursor/mcp.json",
        mcp_support=True,
        cli_command="cursor mcp add",
        description="AI-first code editor",
    ),
    AgentType.WINDSURF: AgentInfo(
        name="Windsurf",
        agent_type=AgentType.WINDSURF,
        config_file="~/.windsurf/mcp.json",
        mcp_support=True,
        cli_command="windsurf mcp add",
        description="AI-powered code editor",
    ),
    AgentType.COPILOT: AgentInfo(
        name="GitHub Copilot",
        agent_type=AgentType.COPILOT,
        config_file="~/.copilot/mcp-config.json",
        mcp_support=True,
        cli_command="copilot",
        description="GitHub AI pair programmer - MCP via copilot-mcp-server",
    ),
    AgentType.CODEX: AgentInfo(
        name="Codex",
        agent_type=AgentType.CODEX,
        config_file="~/.codex/config.toml",
        mcp_support=True,
        cli_command="codex mcp add",
        description="OpenAI coding agent",
    ),
    AgentType.ZED: AgentInfo(
        name="Zed",
        agent_type=AgentType.ZED,
        config_file="~/.zed/settings.json",
        mcp_support=True,
        cli_command="zed mcp add",
        description="High-performance code editor",
    ),
    AgentType.CONTINUE: AgentInfo(
        name="Continue.dev",
        agent_type=AgentType.CONTINUE,
        config_file="~/.continue/config.json",
        mcp_support=True,
        cli_command="continue mcp add",
        description="Open-source AI code assistant",
    ),
    AgentType.AUGMENT: AgentInfo(
        name="Augment",
        agent_type=AgentType.AUGMENT,
        config_file="~/.augment/settings.json",
        mcp_support=True,
        cli_command="auggie",
        description="AI-native coding platform by Augment Code",
    ),
    AgentType.OPENCODE: AgentInfo(
        name="OpenCode",
        agent_type=AgentType.OPENCODE,
        config_file="~/.config/opencode/opencode.jsonc",
        mcp_support=True,
        cli_command="opencode mcp add",
        description="Open-source AI coding agent (opencode.ai)",
    ),
    AgentType.ANTIGRAVITY: AgentInfo(
        name="Antigravity",
        agent_type=AgentType.ANTIGRAVITY,
        config_file="~/.gemini/config/mcp_config.json",
        mcp_support=True,
        cli_command="",  # no CLI add subcommand; config is injected into mcp_config.json
        description="Google Antigravity agentic IDE/CLI (agy)",
    ),
}


class AgentWizard:
    """Setup wizard for AI coding agents."""

    # OpenClaw config file locations
    OPENCLAW_CONFIG_FILES = [
        "~/.openclaw/openclaw.json",
        "~/.config/openclaw/openclaw.json",
        "./.openclaw/openclaw.json",
    ]

    def __init__(self):
        self.workspace = Path.cwd()

    def get_indexed_projects(self) -> dict[str, list[dict]]:
        """Get all indexed projects from all detected agents."""
        from .agent_parser import get_all_indexed_projects
        return get_all_indexed_projects()

    def _find_openclaw_config(self) -> Path | None:
        """Find OpenClaw configuration file."""
        import os

        # Check environment variable first
        env_path = os.environ.get("OPENCLAW_HOME") or os.environ.get("OPENCLAW_CONFIG")
        if env_path:
            config_file = Path(env_path).expanduser() / "openclaw.json"
            if config_file.exists():
                return config_file

        # Check common locations
        for path_str in self.OPENCLAW_CONFIG_FILES:
            path = Path(path_str).expanduser()
            if path.exists():
                return path

        return None

    def _parse_openclaw_config(self, config_path: Path) -> dict:
        """Parse openclaw.json and extract workspace/agent info."""
        try:
            with open(config_path) as f:
                config = json.load(f)

            result = {
                "config_path": str(config_path),
                "workspace": None,
                "agents": [],
                "skills_path": None,
            }

            # Extract workspace from config
            if "workspace" in config:
                result["workspace"] = config["workspace"]
            elif "agents" in config and "defaults" in config["agents"]:
                if "workspace" in config["agents"]["defaults"]:
                    result["workspace"] = config["agents"]["defaults"]["workspace"]

            # Extract agents list
            if "agents" in config:
                if "list" in config["agents"]:
                    result["agents"] = config["agents"]["list"]
                elif "defaults" in config["agents"]:
                    result["agents"] = [config["agents"]["defaults"]]

            # Extract skills path from config
            if "skills" in config:
                if "load" in config["skills"] and "extraDirs" in config["skills"]["load"]:
                    result["skills_path"] = config["skills"]["load"]["extraDirs"]

            return result
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"[WARNING] Could not parse {config_path}: {e}")
            return {}

    def _find_openclaw_workspace(self) -> Path | None:
        """Find OpenClaw workspace from config."""
        config_path = self._find_openclaw_config()
        if not config_path:
            return None

        config = self._parse_openclaw_config(config_path)

        # Check workspace in config
        if config.get("workspace"):
            workspace = Path(config["workspace"]).expanduser()
            if workspace.exists():
                return workspace

        # Default workspace locations
        default_workspaces = [
            Path.home() / ".openclaw" / "workspace",
            Path.home() / "openclaw-workspace",
            self.workspace,
        ]

        for ws in default_workspaces:
            if ws.exists():
                return ws

        return None

    def _find_openclaw_skills_path(self) -> Path | None:
        """Find OpenClaw skills directory."""
        # Check config for skills path
        config_path = self._find_openclaw_config()
        if config_path:
            config = self._parse_openclaw_config(config_path)
            if config.get("skills_path"):
                for path_str in config["skills_path"]:
                    path = Path(path_str).expanduser()
                    if path.exists():
                        return path

        # Check workspace-relative paths
        workspace = self._find_openclaw_workspace()
        if workspace:
            for rel_path in ["skills", ".agents/skills"]:
                full_path = workspace / rel_path
                if full_path.exists():
                    return full_path

        # Check default locations
        default_paths = [
            Path.home() / ".openclaw" / "skills",
            Path.home() / ".agents" / "skills",
        ]

        for path in default_paths:
            if path.exists():
                return path

        return None

    def _find_openclaw_path(self) -> Path | None:
        """Find OpenClaw installation path."""
        # Check config file first
        config_path = self._find_openclaw_config()
        if config_path:
            return config_path.parent

        # Check environment variable
        import os

        env_path = os.environ.get("OPENCLAW_HOME") or os.environ.get("OPENCLAW_CONFIG")
        if env_path:
            path = Path(env_path).expanduser()
            if path.exists():
                return path

        # Check common locations
        common_paths = [
            Path.home() / ".openclaw",
            Path.home() / ".config" / "openclaw",
            self.workspace / ".openclaw",
        ]

        for path in common_paths:
            if path.exists():
                return path

        return None

    def detect_installed_agents(self):
        installed = []
        for agent_type, info in AGENTS.items():
            if agent_type == AgentType.OPENCLAW:
                # Special handling for OpenClaw
                if self._find_openclaw_path():
                    installed.append(agent_type)
            elif agent_type == AgentType.OPENCODE:
                # opencode: detect via install dir or config file
                if (
                    Path.home() / ".opencode" / "bin" / "opencode"
                ).exists() or (Path.home() / ".opencode").exists() or Path(
                    info.config_file
                ).expanduser().exists():
                    installed.append(agent_type)
            elif agent_type == AgentType.ANTIGRAVITY:
                # Antigravity CLI (`agy`); config lives under ~/.gemini
                agy = Path.home() / ".local" / "bin" / "agy"
                if agy.exists() or (Path.home() / ".gemini" / "antigravity-cli").exists():
                    installed.append(agent_type)
            else:
                config_path = Path(info.config_file).expanduser()
                home = Path.home()
                check_path = config_path
                found = False
                while check_path != home and check_path != check_path.parent:
                    if check_path.exists():
                        found = True
                        break
                    check_path = check_path.parent
                if found:
                    installed.append(agent_type)
        return installed

    def get_openclaw_info(self) -> dict:
        """Get detailed OpenClaw information from config."""
        config_path = self._find_openclaw_config()
        if not config_path:
            return {"status": "not_found"}

        config = self._parse_openclaw_config(config_path)
        workspace = self._find_openclaw_workspace()
        skills_path = self._find_openclaw_skills_path()

        return {
            "status": "found",
            "config_path": str(config_path),
            "workspace": str(workspace) if workspace else None,
            "skills_path": str(skills_path) if skills_path else None,
            "agents": config.get("agents", []),
            "raw_config": config,
        }

    def get_agent_info(self, agent_type):
        return AGENTS.get(agent_type)

    def generate_mcp_config(self, agent_type, project_path):
        info = self.get_agent_info(agent_type)
        if not info or not info.mcp_support:
            return {}
        # Note: -w must come BEFORE serve command
        base_config = {
            "codenexus": {"command": "codenexus", "args": ["-w", str(project_path), "serve"]}
        }
        if agent_type in [AgentType.CLAUDE_CODE]:
            return {"mcpServers": base_config}
        elif agent_type == AgentType.OPENCLAW:
            return {
                "skill": {
                    "name": "codenexus",
                    "description": "Search and analyze code using CodeNexus",
                    "allowed_tools": ["bash"],
                    "commands": {
                        "index": f"codenexus index -w {project_path}",
                        "search": "codenexus search",
                        "pipeline": "codenexus pipeline",
                    },
                }
            }
        elif agent_type in [AgentType.HERMES]:
            return {"mcp_servers": base_config}
        elif agent_type == AgentType.CODEX:
            return {"mcp_servers": base_config}
        elif agent_type == AgentType.COPILOT:
            return {"mcpServers": base_config}
        elif agent_type == AgentType.AUGMENT:
            return {"mcpServers": base_config}
        elif agent_type in [AgentType.ZED, AgentType.CONTINUE]:
            return {"mcpServers": base_config}
        # Cursor, Windsurf, OpenCode, Antigravity all use the standard
        # `mcpServers` key (OpenCode uses JSON5 .jsonc, Antigravity uses
        # mcp_config.json — both parsed by the agent parsers).
        elif agent_type in [AgentType.CURSOR, AgentType.WINDSURF, AgentType.ANTIGRAVITY]:
            return {"mcpServers": base_config}
        elif agent_type == AgentType.OPENCODE:
            # OpenCode uses the key `mcp` (not `mcpServers`) and a `command`
            # list plus a `type` field, written to opencode.jsonc (JSON5).
            return {
                "mcp": {
                    "codenexus": {
                        "type": "local",
                        "command": ["codenexus", "-w", str(project_path), "serve"],
                    }
                }
            }
        return {}

    def generate_cli_command(self, agent_type, project_path):
        info = self.get_agent_info(agent_type)
        if not info:
            return "# Unknown agent"
        # Agents without a CLI add subcommand must be configured via their
        # config file; generate_mcp_config already produces the right block.
        if not info.cli_command:
            config = self.generate_mcp_config(agent_type, project_path)
            return (
                f"# {info.name} has no CLI 'mcp add' command.\n"
                f"# Inject this into {info.config_file}:\n"
                f"{json.dumps(config, indent=2)}"
            )
        # Note: -w must come BEFORE serve command
        return f"{info.cli_command} codenexus -- codenexus -w {project_path} serve"

    def print_detected_agents(self):
        installed = self.detect_installed_agents()
        if not installed:
            print("No AI coding agents detected.")
            return
        print(f"Detected {len(installed)} AI coding agent(s):")
        for agent_type in installed:
            info = self.get_agent_info(agent_type)
            print(f"  + {info.name}")

    def print_setup_guide(self, agent_type, project_path):
        info = self.get_agent_info(agent_type)
        if not info:
            print(f"Unknown agent: {agent_type}")
            return
        print(f"\n{'=' * 60}")
        print(f"  {info.name} Setup Guide")
        print(f"{'=' * 60}")
        print(f"\nDescription: {info.description}")
        print(f"Config file: {info.config_file}")
        if info.mcp_support:
            print("\nMCP/Skill Configuration:")
            config = self.generate_mcp_config(agent_type, project_path)
            print(json.dumps(config, indent=2))
        if info.cli_command:
            print("\nCLI Command:")
            cmd = self.generate_cli_command(agent_type, project_path)
            print(cmd)
        # Special instructions for OpenClaw
        if agent_type == AgentType.OPENCLAW:
            print("\nOpenClaw Skill Setup:")
            print("1. Create skill directory:")
            print("   mkdir -p ~/.openclaw/workspace/skills/codenexus")
            print("\n2. Create SKILL.md with the configuration above")
            print("\n3. Use in OpenClaw:")
            print("   /codenexus search 'authentication middleware'")
            print("   /codenexus pipeline 'fix login bug'")
        print(f"\n{'=' * 60}\n")

    @staticmethod
    def _ask_input(prompt, default=None):
        """EOF-safe prompt. Returns the default (or '') on EOF/error."""
        suffix = f" [{default}]" if default is not None else ""
        try:
            val = input(f"{prompt}{suffix}: ").strip()
        except (EOFError, OSError):
            val = ""
        if not val and default is not None:
            return str(default)
        return val

    def interactive_setup(self):
        print("\n=== CodeNexus Agent Setup Wizard ===\n")
        installed = self.detect_installed_agents()

        if not installed:
            print("No AI coding agents detected.")
            print("Please install at least one AI coding agent first.")
            return

        print(f"Detected {len(installed)} AI coding agent(s):")
        for i, agent_type in enumerate(installed, 1):
            info = self.get_agent_info(agent_type)
            print(f"  {i}. {info.name}")

        print()
        choice = self._ask_input("Select agent number", "1")

        try:
            idx = int(choice) - 1
        except ValueError:
            print("Invalid input.")
            return
        if not (0 <= idx < len(installed)):
            print("Invalid selection.")
            return

        selected_agent = installed[idx]

        print(
            "\nSetup mode:\n"
            "  1) Single project (one index)\n"
            "  2) Multi-repo workspace (multiple indexes via ONE agent registration)\n"
        )
        mode = self._ask_input("Select mode", "1")
        if mode == "2":
            self._interactive_multi_setup(selected_agent)
            return

        # Mode 1: single project (existing behaviour)
        project_path = self._ask_input("Project path", str(self.workspace))

        # Show setup guide
        self.print_setup_guide(selected_agent, Path(project_path))

        # Ask to apply
        apply = self._ask_input("Apply configuration automatically? (y/n)", "n").lower()
        if apply in ("y", "yes"):
            self.apply_config(selected_agent, Path(project_path))
            print("\n[SUCCESS] Configuration applied!")
        else:
            print("\n[INFO] Configuration not applied. Use the commands above manually.")

    def _interactive_multi_setup(self, agent_type):
        """Interactive flow for registering several repos with one agent."""
        info = self.get_agent_info(agent_type)
        print(f"\n[INFO] Configuring {info.name} with a multi-repo workspace.")

        default_root = str(self.workspace)
        root_str = self._ask_input("Workspace root", default_root)
        workspace_root = Path(root_str).expanduser().resolve()

        default_name = workspace_root.name or "workspace"
        self._ask_input("Workspace name", default_name)  # name is cosmetic for now

        repos: list[tuple[str, Path]] = []
        print("\nAdd repositories (empty path to finish):")
        while True:
            path_str = self._ask_input("  Repo path", "")
            if not path_str:
                if not repos:
                    print("  [ERROR] Add at least one repository.")
                    continue
                break
            p = Path(path_str).expanduser()
            if not p.exists():
                print(f"  [WARNING] path does not exist: {p}")
                continue
            alias = self._ask_input("  Alias", p.name)
            repos.append((alias, p))

        print()
        self.print_setup_guide(agent_type, workspace_root)

        apply = self._ask_input(
            "Apply configuration and index all repos? (y/n)", "n"
        ).lower()
        if apply in ("y", "yes"):
            ok = self.apply_config_multi(agent_type, workspace_root, repos)
            if ok:
                print(
                    f"\n[SUCCESS] Multi-repo workspace configured for {info.name}!\n"
                    f"  {len(repos)} repo(s) served via: codenexus -w "
                    f"{workspace_root} serve"
                )
            else:
                print("\n[ERROR] Configuration failed. See messages above.")
        else:
            print("\n[INFO] Configuration not applied. Use the commands above manually.")

    def apply_config(self, agent_type, project_path):
        """Apply configuration for a single project, then index it."""
        result = self._write_agent_config(agent_type, project_path)
        if result:
            self._auto_index(project_path)
        return result

    def _write_agent_config(self, agent_type, project_path):
        """Write the MCP/skill config for one agent pointing at ``project_path``.

        No indexing happens here — callers decide whether/what to index. This
        is shared by the single-project flow and the multi-repo flow (which
        points the agent at a federated workspace root instead of one repo).
        """
        info = self.get_agent_info(agent_type)
        if not info:
            return False

        config = self.generate_mcp_config(agent_type, project_path)
        if not config:
            print(f"[WARNING] No configuration to apply for {info.name}")
            return False

        if agent_type == AgentType.OPENCLAW:
            return self._apply_openclaw_config(config, project_path)
        if info.mcp_support:
            return self._apply_mcp_config(info, config)
        return False

    def apply_config_multi(self, agent_type, workspace_root, repos):
        """Register several repos with one agent via a federated workspace.

        Creates (or opens) the workspace at ``workspace_root``, adds each
        repo, indexes all members, then writes the agent config pointing at
        the workspace root — so a single ``-w <workspace_root> serve``
        registration serves every repo through the federated graph.

        Args:
            agent_type: the agent to configure.
            workspace_root: directory that will hold ``.codenexus/workspace.json``
                and the per-member index DBs. Created if missing.
            repos: list of ``(alias, path)`` tuples.

        Returns:
            True if the agent config was written.
        """
        from .workspace import MultiRepoWorkspace, WorkspaceConfig

        workspace_root = Path(workspace_root)
        workspace_root.mkdir(parents=True, exist_ok=True)
        ws = MultiRepoWorkspace(workspace_root)

        if not ws.config:
            if not getattr(ws, "_config_load_ok", True):
                print(
                    f"[ERROR] Existing workspace at {workspace_root} is corrupt; "
                    f"fix or remove {ws.config_path} first."
                )
                return False
            ws.config = WorkspaceConfig(name=workspace_root.name or "workspace")
            ws.save_config()

        added = 0
        for alias, path in repos:
            alias = (alias or "").strip()
            if not alias:
                alias = Path(str(path)).name
            p = Path(str(path)).expanduser()
            if not p.exists():
                print(f"[WARNING] Path does not exist, skipping: {p}")
                continue
            if ws.add_repo(alias, p):
                added += 1
            else:
                print(f"[WARNING] Could not add repo '{alias}' (already registered?)")

        if added == 0:
            print("[ERROR] No repositories were added to the workspace.")
            return False

        print(f"\n[INFO] Indexing {added} repo(s)...")
        try:
            results = ws.index_all()
        finally:
            # Flush/close member graphs so the DBs are released before the
            # MCP server (or a later query) re-opens them read-only.
            for graph in list(ws.graphs.values()):
                try:
                    graph.close()
                except Exception:
                    pass
            ws.graphs.clear()
        for alias, count in results.items():
            print(f"  {alias}: {count} files")

        return self._write_agent_config(agent_type, workspace_root)

    def _auto_index(self, project_path):
        """Automatically index the project after config."""
        import subprocess

        print(f"\n[INFO] Indexing project: {project_path}")
        try:
            result = subprocess.run(
                ["codenexus", "-w", str(project_path), "index"],
                capture_output=True,
                encoding="utf-8",
                timeout=120,
            )
            if result.returncode == 0:
                print("[SUCCESS] Project indexed successfully")
            else:
                print("[WARNING] Indexing completed with warnings")
        except subprocess.TimeoutExpired:
            print("[WARNING] Indexing timed out")
        except FileNotFoundError:
            print("[WARNING] codenexus not found in PATH")

    def _apply_openclaw_config(self, config, project_path):
        """Apply OpenClaw skill configuration."""
        # Find skills path from config or default locations
        skills_path = self._find_openclaw_skills_path()

        if not skills_path:
            # Try to find workspace and create skills there
            workspace = self._find_openclaw_workspace()
            if workspace:
                skills_path = workspace / "skills"
            else:
                # Fallback to default location
                skills_path = Path.home() / ".openclaw" / "skills"

            skills_path.mkdir(parents=True, exist_ok=True)
            print(f"[INFO] Created skills directory: {skills_path}")

        skill_dir = skills_path / "codenexus"
        skill_file = skill_dir / "SKILL.md"

        # Create directory
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Generate SKILL.md content
        skill_content = f"""---
name: codenexus
description: Search and analyze code using CodeNexus
allowed_tools:
  - bash
---

# CodeNexus Skill

Use CodeNexus to search and analyze code in the workspace.

## Commands

- `codenexus index -w {project_path}` - Index the workspace
- `codenexus search "query"` - Search for code
- `codenexus pipeline "task"` - Get context for a task
- `codenexus status` - Check index status
"""

        # Write SKILL.md
        with open(skill_file, "w") as f:
            f.write(skill_content)

        print(f"[SUCCESS] Created skill: {skill_file}")
        print(f"[INFO] Skill will be available to all agents in: {skills_path}")
        return True

    def _apply_mcp_config(self, info, config):
        """Apply MCP configuration for an agent."""
        config_path = Path(info.config_file).expanduser()

        # Guard against unsupported config file formats (e.g. .md) so we
        # never overwrite an unrelated file with JSON/MCP content.
        supported = {".json", ".jsonc", ".yaml", ".yml", ".toml"}
        if config_path.suffix not in supported:
            print(
                f"[WARNING] {config_path} has an unsupported format "
                f"({config_path.suffix or 'none'}). Skipping automatic write. "
                f"Configure {info.name} manually with: {info.cli_command or 'its config file'}"
            )
            return False

        # Create parent directory
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine file format
        is_jsonc = config_path.suffix == ".jsonc"
        is_yaml = config_path.suffix in [".yaml", ".yml"]
        is_toml = config_path.suffix == ".toml"

        # Load existing config or create new
        existing_config = {}
        if config_path.exists():
            try:
                if is_yaml:
                    import yaml

                    with open(config_path) as f:
                        existing_config = yaml.safe_load(f) or {}
                elif is_toml:
                    try:
                        import tomllib
                    except ImportError:
                        import tomli as tomllib
                    with open(config_path, "rb") as f:
                        existing_config = tomllib.load(f)
                elif is_jsonc:
                    existing_config = _load_jsonc(config_path)
                else:
                    with open(config_path) as f:
                        existing_config = json.load(f)
            except Exception as e:
                # An existing but unreadable config must NEVER be overwritten:
                # falling through with {} used to replace the whole file
                # (e.g. ~/.claude.json session state) with near-empty content.
                print(f"[ERROR] {config_path} exists but could not be read ({e}).")
                print("[ERROR] Aborting: fix or remove the file manually, then retry.")
                return False

        # Back up the previous content before touching anything (skip when
        # creating a brand-new config file — there is nothing to back up).
        if config_path.exists():
            backup_path = config_path.with_suffix(config_path.suffix + ".codenexus-backup")
            try:
                backup_path.write_bytes(config_path.read_bytes())
            except OSError as e:
                print(f"[WARNING] Could not back up {config_path}: {e}")

        # Merge configs
        for key, value in config.items():
            if key in existing_config:
                if isinstance(existing_config[key], dict) and isinstance(value, dict):
                    existing_config[key].update(value)
                else:
                    existing_config[key] = value
            else:
                existing_config[key] = value

        # Write config in appropriate format
        try:
            if is_yaml:
                import yaml

                with open(config_path, "w") as f:
                    yaml.dump(existing_config, f, default_flow_style=False, allow_unicode=True)
            elif is_toml:
                try:
                    import tomli_w
                except ImportError:
                    print("[WARNING] tomli-w not installed. Installing...")
                    import subprocess

                    subprocess.check_call([sys.executable, "-m", "pip", "install", "tomli-w"])
                    import tomli_w
                with open(config_path, "wb") as f:
                    tomli_w.dump(existing_config, f)
            else:
                with open(config_path, "w") as f:
                    json.dump(existing_config, f, indent=2)

            print(f"[SUCCESS] Updated {config_path}")
            return True
        except Exception as e:
            print(f"[ERROR] Could not write {config_path}: {e}")
            return False


def get_agent_by_name(name):
    name_lower = name.lower()
    for agent_type, info in AGENTS.items():
        if name_lower in info.name.lower() or name_lower == agent_type.value:
            return agent_type
    return None
