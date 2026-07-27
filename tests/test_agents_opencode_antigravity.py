"""Agent integration tests: OpenCode and Antigravity (productization)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def project(tmp_path):
    """A small indexable project."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "auth.py").write_text(
        "def login(user):\n    return user.token\n\n"
        "def authenticate(req):\n    return req.ok\n"
    )
    subprocess.run(
        ["codenexus", "-w", str(proj), "index"], check=True, capture_output=True
    )
    return proj


# --------------------------------------------------------------------------- #
# Wizard registry
# --------------------------------------------------------------------------- #
def test_opencode_in_registry():
    from codenexus.wizard import AGENTS, AgentType

    assert AgentType.OPENCODE in AGENTS
    assert AGENTS[AgentType.OPENCODE].mcp_support is True
    assert AGENTS[AgentType.OPENCODE].cli_command == "opencode mcp add"


def test_antigravity_in_registry():
    from codenexus.wizard import AGENTS, AgentType

    assert AgentType.ANTIGRAVITY in AGENTS
    assert AGENTS[AgentType.ANTIGRAVITY].mcp_support is True
    # Antigravity has no CLI `mcp add`; config is injected into mcp_config.json
    assert AGENTS[AgentType.ANTIGRAVITY].cli_command == ""


# --------------------------------------------------------------------------- #
# Config generation per agent
# --------------------------------------------------------------------------- #
def test_opencode_mcp_config_shape(tmp_path):
    from codenexus.wizard import AgentWizard, AgentType

    cfg = AgentWizard().generate_mcp_config(AgentType.OPENCODE, tmp_path)
    # OpenCode nests under `mcp` with a `command` list, not `mcpServers`.
    assert "mcp" in cfg
    srv = cfg["mcp"]["codenexus"]
    assert srv["type"] == "local"
    assert srv["command"] == ["codenexus", "-w", str(tmp_path), "serve"]


def test_antigravity_mcp_config_shape(tmp_path):
    from codenexus.wizard import AgentWizard, AgentType

    cfg = AgentWizard().generate_mcp_config(AgentType.ANTIGRAVITY, tmp_path)
    assert cfg == {
        "mcpServers": {
            "codenexus": {
                "command": "codenexus",
                "args": ["-w", str(tmp_path), "serve"],
            }
        }
    }


def test_antigravity_cli_command_is_manual_injection(tmp_path):
    from codenexus.wizard import AgentWizard, AgentType

    cmd = AgentWizard().generate_cli_command(AgentType.ANTIGRAVITY, tmp_path)
    # No `mcp add` subcommand -> must instruct manual config injection.
    assert "no CLI" in cmd
    assert "mcp_config.json" in cmd


# --------------------------------------------------------------------------- #
# JSON5 (opencode.jsonc) loader
# --------------------------------------------------------------------------- #
def test_load_jsonc_strips_comments(tmp_path):
    from codenexus.wizard import _load_jsonc

    p = tmp_path / "opencode.jsonc"
    p.write_text(
        '{\n  // line comment\n'
        '  "mcp": { "codenexus": {"type": "local", '
        '"command": ["codenexus", "-w", "/x", "serve"]} }\n}\n'
    )
    data = _load_jsonc(p)
    assert data["mcp"]["codenexus"]["command"] == ["codenexus", "-w", "/x", "serve"]


# --------------------------------------------------------------------------- #
# Agent parsers read back what wizard wrote
# --------------------------------------------------------------------------- #
def test_opencode_parser_reads_real_config(tmp_path):
    from codenexus.agent_parser import OpenCodeParser

    cfg_path = tmp_path / "opencode.jsonc"
    cfg_path.write_text(
        json.dumps(
            {
                "mcp": {
                    "codenexus": {
                        "type": "local",
                        "command": ["codenexus", "-w", str(tmp_path), "serve"],
                    }
                }
            }
        )
    )
    projects = OpenCodeParser().parse(cfg_path)
    assert len(projects) == 1
    assert projects[0]["path"] == str(tmp_path)


def test_antigravity_parser_reads_real_config(tmp_path):
    from codenexus.agent_parser import AntigravityParser

    cfg_path = tmp_path / "mcp_config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "codenexus": {
                        "command": "codenexus",
                        "args": ["-w", str(tmp_path), "serve"],
                    }
                }
            }
        )
    )
    projects = AntigravityParser().parse(cfg_path)
    assert len(projects) == 1
    assert projects[0]["path"] == str(tmp_path)


def test_get_all_indexed_projects_includes_new_agents(tmp_path):
    from codenexus.agent_parser import get_all_indexed_projects

    cfg = tmp_path / "opencode.jsonc"
    cfg.write_text(
        json.dumps(
            {"mcp": {"codenexus": {"type": "local", "command": ["codenexus", "-w", str(tmp_path), "serve"]}}}
        )
    )
    # point the parser at our temp file by monkeypatching its search paths
    from codenexus import agent_parser

    parser = agent_parser.OpenCodeParser()
    parser.config_paths = [cfg]
    projects = parser.get_indexed_projects()
    assert len(projects) == 1
    assert projects[0]["path"] == str(tmp_path)
