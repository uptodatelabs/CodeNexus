"""Setup wizard for AI coding agent integration."""

import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from enum import Enum

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
        description="Personal AI assistant with messaging integration"
    ),
    AgentType.HERMES: AgentInfo(
        name="Hermes Agent",
        agent_type=AgentType.HERMES,
        config_file="~/.hermes/config.yaml",
        mcp_support=True,
        cli_command="hermes mcp add",
        description="Self-improving AI agent by Nous Research"
    ),
    AgentType.CURSOR: AgentInfo(
        name="Cursor",
        agent_type=AgentType.CURSOR,
        config_file="~/.cursor/mcp.json",
        mcp_support=True,
        cli_command="cursor mcp add",
        description="AI-first code editor"
    ),
    AgentType.WINDSURF: AgentInfo(
        name="Windsurf",
        agent_type=AgentType.WINDSURF,
        config_file="~/.windsurf/mcp.json",
        mcp_support=True,
        cli_command="windsurf mcp add",
        description="AI-powered code editor"
    ),
    AgentType.COPILOT: AgentInfo(
        name="GitHub Copilot",
        agent_type=AgentType.COPILOT,
        config_file="~/.github/copilot-instructions.md",
        mcp_support=True,
        cli_command="copilot",
        description="GitHub AI pair programmer - MCP via copilot-mcp-server"
    ),
    AgentType.CODEX: AgentInfo(
        name="Codex",
        agent_type=AgentType.CODEX,
        config_file="~/.codex/config.toml",
        mcp_support=True,
        cli_command="codex mcp add",
        description="OpenAI coding agent"
    ),
    AgentType.ZED: AgentInfo(
        name="Zed",
        agent_type=AgentType.ZED,
        config_file="~/.zed/settings.json",
        mcp_support=True,
        cli_command="zed mcp add",
        description="High-performance code editor"
    ),
    AgentType.CONTINUE: AgentInfo(
        name="Continue.dev",
        agent_type=AgentType.CONTINUE,
        config_file="~/.continue/config.json",
        mcp_support=True,
        cli_command="continue mcp add",
        description="Open-source AI code assistant"
    ),
    AgentType.AUGMENT: AgentInfo(
        name="Augment",
        agent_type=AgentType.AUGMENT,
        config_file="~/.augment/settings.json",
        mcp_support=True,
        cli_command="auggie",
        description="AI-native coding platform by Augment Code"
    ),
}

class AgentWizard:
    def __init__(self):
        self.workspace = Path.cwd()

    def detect_installed_agents(self):
        installed = []
        for agent_type, info in AGENTS.items():
            config_path = Path(info.config_file).expanduser()
            # Check if config file exists OR immediate parent directories exist
            # Stop at home directory to avoid false positives
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

    def get_agent_info(self, agent_type):
        return AGENTS.get(agent_type)

    def generate_mcp_config(self, agent_type, project_path):
        info = self.get_agent_info(agent_type)
        if not info or not info.mcp_support:
            return {}
        base_config = {
            "codenexus": {
                "command": "codenexus",
                "args": ["serve", "-w", str(project_path)]
            }
        }
        if agent_type in [AgentType.CLAUDE_CODE]:
            return {"mcpServers": base_config}
        elif agent_type == AgentType.OPENCLAW:
            return {"skill": {
                "name": "codenexus",
                "description": "Search and analyze code using CodeNexus",
                "allowed_tools": ["bash"],
                "commands": {
                    "index": f"codenexus index -w {project_path}",
                    "search": f"codenexus search",
                    "pipeline": f"codenexus pipeline"
                }
            }}
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
        return f"{info.cli_command} codenexus -- codenexus serve -w {project_path}"

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
        print(f"\n{'='*60}")
        print(f"  {info.name} Setup Guide")
        print(f"{'='*60}")
        print(f"\nDescription: {info.description}")
        print(f"Config file: {info.config_file}")
        if info.mcp_support:
            print(f"\nMCP/Skill Configuration:")
            config = self.generate_mcp_config(agent_type, project_path)
            print(json.dumps(config, indent=2))
        if info.cli_command:
            print(f"\nCLI Command:")
            cmd = self.generate_cli_command(agent_type, project_path)
            print(cmd)
        # Special instructions for OpenClaw
        if agent_type == AgentType.OPENCLAW:
            print(f"\nOpenClaw Skill Setup:")
            print(f"1. Create skill directory:")
            print(f"   mkdir -p ~/.openclaw/workspace/skills/codenexus")
            print(f"\n2. Create SKILL.md with the configuration above")
            print(f"\n3. Use in OpenClaw:")
            print(f"   /codenexus search 'authentication middleware'")
            print(f"   /codenexus pipeline 'fix login bug'")
        print(f"\n{'='*60}\n")

    def interactive_setup(self):
        print("\n=== CodeNexus Agent Setup Wizard ===\n")
        installed = self.detect_installed_agents()
        if not installed:
            print("No AI coding agents detected.")
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
                self.print_setup_guide(selected_agent, Path(project_path))
            else:
                print("Invalid selection.")
        except ValueError:
            print("Invalid input.")

def get_agent_by_name(name):
    name_lower = name.lower()
    for agent_type, info in AGENTS.items():
        if name_lower in info.name.lower() or name_lower == agent_type.value:
            return agent_type
    return None
