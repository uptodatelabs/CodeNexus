# CodeNexus AI

**The context engine for AI coding agents**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/codenexus-ai.svg)](https://pypi.org/project/codenexus-ai/)

[English](README.md) | [한국어](README.ko.md)

---

## What is CodeNexus?

CodeNexus is a **local-first context engine** that helps AI coding agents understand your codebase better. It builds a live dependency graph of your code and serves only the relevant context to AI agents, reducing token usage by **50-70%** while improving code quality.

### Key Features

- **Local-first**: Your code never leaves your machine
- **Token reduction**: Cut AI context tokens by up to ~99% (real-world measured: 951K → ~4.3K per task on a 211-file project)
- **Multi-language**: Python, JavaScript, TypeScript support
- **MCP compatible**: Built on the official `mcp` Python SDK (standard `Content-Length` framed stdio). Works with Hermes, Claude Code, Cursor, Windsurf, Zed, Continue.dev, GitHub Copilot, Codex, Augment, and any spec-compliant MCP client.
- **Fast indexing**: SQLite-based dependency graph

---

## Quick Start

### Installation

```bash
pip install codenexus-ai
```

**Developing from source (recommended for local edits):** install in editable
mode so changes in this repo are picked up immediately. A non-editable
`pip install .` copies the code into `site-packages` and will silently keep
running the old copy even after you edit files here.

```bash
git clone https://github.com/uptodatelabs/CodeNexus.git
cd CodeNexus
pip install -e .
```

### Basic Usage

```bash
# Index your project
codenexus index

# Search for context
codenexus search "authentication middleware"

# Run context pipeline
codenexus pipeline "fix login bug"

# Check index status
codenexus status
```

---

## How It Works

```
Your Codebase
     ↓
[CodeNexus Indexer]
     ↓
┌─────────────────────────────────────┐
│  Dependency Graph (SQLite + FTS5)   │
│  - Functions, Classes, Imports      │
│  - Call relationships               │
│  - Type information                 │
└─────────────────────────────────────┘
     ↓
[Context Capsule Generator]
     ↓
┌─────────────────────────────────────┐
│  Optimized Context for AI Agent     │
│  - Pivot files: Full source         │
│  - Supporting: Skeleton only        │
│  - Token budget: Respected          │
└─────────────────────────────────────┘
     ↓
AI Agent (Claude Code, Cursor, etc.)
```

---

## Claude Code Integration

CodeNexus works with Claude Code to reduce token usage for AI coding agents.

### Setup

#### 1. Install CodeNexus

```bash
pip install codenexus-ai
```

#### 2. Edit `.claude.json`

**File location:**
- macOS/Linux: `~/.claude.json`
- Windows: `C:\Users\your-username\.claude.json`

#### 3. Add configuration

Add the following to your `~/.claude.json`:

```json
{
  "mcpServers": {
    "codenexus": {
      "command": "codenexus",
      "args": ["-w", "/path/to/your/project", "serve"]
    }
  }
}
```

**⚠️ Important: `/path/to/your/project` should be the path to the project where you want to use CodeNexus.**

### Path Examples

**❌ Wrong:**
```json
"args": ["-w", "C:\\Users\\username\\.codenexus", "serve"]
```
→ CodeNexus config directory (incorrect)

**✅ Correct:**
```json
"args": ["-w", "C:\\Users\\username\\projects\\my-app", "serve"]
```
→ Project directory where you want to use CodeNexus

### OS-specific Path Examples

**Windows:**
```json
{
  "mcpServers": {
    "codenexus": {
      "command": "codenexus",
      "args": ["-w", "C:\\Users\\username\\projects\\my-app", "serve"]
    }
  }
}
```

**macOS/Linux:**
```json
{
  "mcpServers": {
    "codenexus": {
      "command": "codenexus",
      "args": ["-w", "/home/username/projects/my-app", "serve"]
    }
  }
}
```

### Multiple Projects

To use CodeNexus with multiple projects, add configuration for each project:

```json
{
  "projects": {
    "C:\\Users\\username\\projects\\app1": {
      "mcpServers": {
        "codenexus": {
          "command": "codenexus",
          "args": ["-w", "C:\\Users\\username\\projects\\app1", "serve"]
        }
      }
    },
    "C:\\Users\\username\\projects\\app2": {
      "mcpServers": {
        "codenexus": {
          "command": "codenexus",
          "args": ["-w", "C:\\Users\\username\\projects\\app2", "serve"]
        }
      }
    }
  }
}
```

### Verify Setup

1. Save `.claude.json`
2. Restart Claude Code
3. Run Claude in your project directory

```bash
cd C:\Users\username\projects\my-app
claude
```

### Troubleshooting

**If MCP server doesn't connect:**

CodeNexus speaks the **standard MCP stdio protocol** (built on the official `mcp` Python SDK with `Content-Length` framed JSON-RPC), so any spec-compliant client (Hermes, Claude Code, Cursor, Windsurf, Zed, Continue.dev, GitHub Copilot, Codex, Augment) connects out of the box.

1. Check if CodeNexus is installed:
   ```bash
   pip show codenexus-ai
   ```

2. Test code execution:
   ```bash
   codenexus --version
   ```

3. Verify the path is correct (watch for quotes)

---

## Supported Languages

| Language | Status |
|----------|--------|
| Python | ✅ Full support |
| JavaScript | ✅ Full support |
| TypeScript | ✅ Full support |
| Go | ✅ Full support |
| Rust | ✅ Full support |
| Java | ✅ Full support |
| C# | ✅ Full support |

---

## Supported AI Agents

CodeNexus integrates with AI coding agents via MCP (or skills for OpenClaw). The
setup wizard auto-detects installed agents and writes the correct config format
for each.

| Agent | Config file | MCP key |
|-------|-------------|---------|
| Claude Code | `~/.claude.json` | `mcpServers` |
| Cursor | `~/.cursor/mcp.json` | `mcpServers` |
| Windsurf | `~/.windsurf/mcp.json` | `mcpServers` |
| GitHub Copilot | `~/.copilot/mcp-config.json` | `mcpServers` |
| Zed | `~/.zed/settings.json` | `mcpServers` |
| Continue.dev | `~/.continue/config.json` | `mcpServers` |
| Augment | `~/.augment/settings.json` | `mcpServers` |
| Hermes Agent | `~/.hermes/config.yaml` | `mcp_servers` |
| Codex | `~/.codex/config.toml` | `mcp_servers` |
| OpenClaw | `~/.openclaw/workspace/skills/codenexus/SKILL.md` | skill |

## Other AI Agent Integration

CodeNexus works with various AI coding agents. Here's how to integrate with other popular tools.

### OpenClaw Integration

[OpenClaw](https://github.com/openclaw/openclaw) is a personal AI assistant that connects to WhatsApp, Telegram, Slack, Discord, and more.

#### Setup

OpenClaw doesn't support MCP directly. Use CodeNexus CLI commands through OpenClaw's skill system.

**1. Install CodeNexus:**

```bash
pip install codenexus-ai
```

**2. Create OpenClaw skill:**

Create `~/.openclaw/workspace/skills/codenexus/SKILL.md`:

```markdown
---
name: codenexus
description: Search and analyze code using CodeNexus
allowed_tools:
  - bash
---

# CodeNexus Skill

Use CodeNexus to search and analyze code in the workspace.

## Commands

- `codenexus index` - Index the workspace
- `codenexus search "query"` - Search for code
- `codenexus pipeline "task"` - Get context for a task
```

**3. Usage in OpenClaw:**

```
/codenexus search "authentication middleware"
/codenexus pipeline "fix login bug"
```

### Hermes Agent Integration

[Hermes Agent](https://github.com/NousResearch/hermes-agent) is a self-improving AI agent by Nous Research.

#### Setup

Hermes supports MCP servers. Configure CodeNexus as an MCP server.

**1. Install CodeNexus:**

```bash
pip install codenexus-ai
```

**2. Add MCP server to Hermes:**

```bash
hermes mcp add codenexus -- codenexus -w /path/to/your/project serve
```

Or add to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  codenexus:
    command: codenexus
    args:
      - serve
      - -w
      - /path/to/your/project
```

**3. Usage in Hermes:**

```
/hermes search "authentication middleware"
/hermes pipeline "fix login bug"
```

### Other Agents

Any agent that supports CLI commands can use CodeNexus:

```bash
# Direct CLI usage
codenexus index
codenexus search "query"
codenexus pipeline "task"
codenexus status
```

The `pipeline` command prints a **human-readable context capsule** (task,
detected intent, token estimate, pivot-file panels, and a skeleton tree) rather
than raw JSON. Programmatic clients (MCP agents) receive the same data as a
structured JSON payload via the `run_pipeline` tool.

---

## Token Savings Example

Measured on the `openclaw_workspace/projects` index (211 files, 4,224 nodes, 62,194 edges):

**Sending the entire codebase to the model:**
```
951,322 tokens (full source: Python + JS/TS)
```

**Asking CodeNexus for context on a task** (`run_pipeline`, avg over 5 real tasks):
```
~4,325 tokens per task
```

**Reduction: ~99.5%** — only the files/definitions relevant to the task are returned.

> The exact number depends on project size and task scope. CodeNexus always
> returns the *relevant* slice, not the whole tree.

---

## Setup Wizard

CodeNexus includes a setup wizard to easily configure AI coding agents.

### Detect Installed Agents

```bash
codenexus wizard detect
```

### List Supported Agents

```bash
codenexus wizard list
```

### Setup a Specific Agent

```bash
# Claude Code
codenexus wizard setup claude_code

# OpenClaw
codenexus wizard setup openclaw

# Hermes Agent
codenexus wizard setup hermes

# Cursor
codenexus wizard setup cursor

# GitHub Copilot
codenexus wizard setup copilot

# Codex
codenexus wizard setup codex

# And more...
```

**Note:** Setup will automatically index your project after configuration.

### Clear Index Data

```bash
codenexus wizard clear
```

This will show all index directories and let you select which ones to clear.

For non-interactive use (e.g. scripts/CI), clear everything without prompts:

```bash
codenexus wizard clear --all --yes
```

- `--all` selects every discovered index
- `--yes` skips the confirmation prompt

You can also clear specific indexes by typing their IDs (e.g. `idx-1,idx-3`)
or type the project directory name to confirm each deletion individually.

### Interactive Setup

```bash
codenexus wizard interactive
```

---

## Roadmap

- [x] Tree-sitter integration for better parsing
- [x] Graph centrality (PageRank) for better ranking
- [x] Local LLM support for additional savings
- [x] Multi-repo workspace support
- [ ] VS Code extension

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

CodeNexus uses an optional **license tier** that gates features at runtime
(checked by `CodeNexusServer` on startup). Tiers are enforced automatically —
no code changes needed:

| Feature            | Free            | Pro / Team / Enterprise |
|--------------------|-----------------|--------------------------|
| Languages          | Python, JS, TS  | All 7 (incl. Go, Rust, Java, C#) |
| Max indexed nodes  | 5,000           | 100,000                  |
| Session memory     | —               | ✅                        |
| Local LLM          | —               | ✅                        |
| Multi-repo         | —               | ✅                        |

Check your tier, or activate a key:

```bash
codenexus license status
codenexus license activate CNX-PRO-<owner>-<YYYYMMDD>
codenexus license features
```

When you run `codenexus serve`, the active tier is printed to stderr:

```
[codenexus] Tier: free | languages: javascript, python, typescript | memory: off | llm: off
```

---

## Acknowledgments

- Inspired by [vexp](https://vexp.dev/) - The original context engine
- Built with Python, SQLite, and MCP
- Thanks to all contributors

---

## Support

If you find CodeNexus useful, consider supporting the project:

[![Ko-fi](https://img.shields.io/badge/Ko--fi-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/uptodatelabs)
[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-CodeNexus-ea4aaa?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/uptodatelabs)

---

**Connect your code. Empower your AI.**
