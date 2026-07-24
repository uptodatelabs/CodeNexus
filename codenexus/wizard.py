"""Setup wizard for AI coding agent integration."""

import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List


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
        config_file=".mcp.json",
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
        config_file="~/.github/copilot-instructions.md",
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
    
    def get_indexed_projects(self) -> Dict[str, List[Dict]]:
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
        elif agent_type in [AgentType.CURSOR, AgentType.WINDSURF]:
            return {"mcpServers": base_config}
        elif agent_type == AgentType.CODEX:
            return {"mcp_servers": base_config}
        elif agent_type == AgentType.COPILOT:
            return {"mcpServers": base_config}
        elif agent_type == AgentType.AUGMENT:
            return {"mcpServers": base_config}
        elif agent_type in [AgentType.ZED, AgentType.CONTINUE]:
            return {"mcpServers": base_config}
        return {}

    def generate_cli_command(self, agent_type, project_path):
        info = self.get_agent_info(agent_type)
        if not info or not info.cli_command:
            return f"# {info.name} requires manual configuration"
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
        choice = input("Select agent number: ").strip()

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(installed):
                selected_agent = installed[idx]
                project_path = input(f"Project path [{self.workspace}]: ").strip()
                if not project_path:
                    project_path = str(self.workspace)

                # Show setup guide
                self.print_setup_guide(selected_agent, Path(project_path))

                # Ask to apply
                apply = input("Apply configuration automatically? (y/n): ").strip().lower()
                if apply == "y" or apply == "yes":
                    self.apply_config(selected_agent, Path(project_path))
                    print("\n[SUCCESS] Configuration applied!")
                else:
                    print("\n[INFO] Configuration not applied. Use the commands above manually.")
            else:
                print("Invalid selection.")
        except ValueError:
            print("Invalid input.")

    def apply_config(self, agent_type, project_path):
        """Apply configuration for an agent."""
        info = self.get_agent_info(agent_type)
        if not info:
            return False

        config = self.generate_mcp_config(agent_type, project_path)
        if not config:
            print(f"[WARNING] No configuration to apply for {info.name}")
            return False

        # Special handling for OpenClaw
        if agent_type == AgentType.OPENCLAW:
            result = self._apply_openclaw_config(config, project_path)
        # For MCP-based agents
        elif info.mcp_support:
            result = self._apply_mcp_config(info, config)
        else:
            result = False

        # Auto-index after successful config
        if result:
            self._auto_index(project_path)

        return result

    def _auto_index(self, project_path):
        """Automatically index the project after config."""
        import subprocess

        print(f"\n[INFO] Indexing project: {project_path}")
        try:
            result = subprocess.run(
                ["codenexus", "-w", str(project_path), "index"],
                capture_output=True,
                text=True,
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

        # Create parent directory
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine file format
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
                else:
                    with open(config_path) as f:
                        existing_config = json.load(f)
            except Exception as e:
                print(f"[WARNING] Could not read {config_path}: {e}")
                existing_config = {}

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
