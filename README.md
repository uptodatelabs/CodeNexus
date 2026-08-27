# CodeNexus AI

**The context engine for AI coding agents**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/codenexus-ai.svg)](https://pypi.org/project/codenexus-ai/)

**English** | [한국어](#korean)

---

## What is CodeNexus?

CodeNexus is a **local-first context engine** that helps AI coding agents understand your codebase better. It builds a live dependency graph of your code and serves only the relevant context to AI agents, reducing token usage by **up to ~99%** (real-world measured) while improving code quality.

### Key Features

- **Local-first**: Your code never leaves your machine
- **Token reduction**: Cut AI context tokens by up to ~99% (real-world measured: 951K → ~4.3K per task on a 211-file project)
- **Multi-language**: Python, JavaScript, TypeScript, Go, Rust, Java, C# (7 languages)
- **MCP compatible**: Built on the official `mcp` Python SDK (standard `Content-Length` framed stdio). Works with Hermes, Claude Code, Cursor, Windsurf, Zed, Continue.dev, GitHub Copilot, Codex, Augment, OpenCode, Antigravity, and any spec-compliant MCP client.
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
| OpenCode | `~/.config/opencode/opencode.jsonc` | `mcp` |
| Antigravity | `~/.gemini/config/mcp_config.json` | `mcpServers` |
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
```bash
/hermes search "authentication middleware"
/hermes pipeline "fix login bug"
```

### OpenCode Integration

[OpenCode](https://opencode.ai/) is an open-source AI coding agent. CodeNexus is wired up with its CLI.

**1. Install CodeNexus:**
```bash
pip install codenexus-ai
```

**2. Add the MCP server (auto-configures `~/.config/opencode/opencode.jsonc`):**
```bash
opencode mcp add codenexus -- codenexus -w /path/to/your/project serve
```

Or let the wizard do it:
```bash
codenexus wizard setup opencode
```

**3. Verify:**
```bash
opencode mcp list
# → ✓ codenexus connected
```

### Antigravity Integration

[Antigravity](https://antigravity.google/) (Google's agentic IDE/CLI, `agy`) supports MCP via its config file. It has no `mcp add` CLI subcommand, so the server block is injected into the config.

**1. Install CodeNexus:**
```bash
pip install codenexus-ai
```

**2. Apply config via the wizard (writes `~/.gemini/config/mcp_config.json`):**
```bash
codenexus wizard setup antigravity
```

Or add manually to `~/.gemini/config/mcp_config.json` (or your workspace `.agents/mcp_config.json`):
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

**3. Reload** in the Antigravity CLI/IDE via `/mcp`, then use CodeNexus through the `run_pipeline` / `get_context_capsule` tools.

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

# OpenCode (open-source CLI)
codenexus wizard setup opencode

# Antigravity (Google agentic IDE/CLI — `agy`)
codenexus wizard setup antigravity

# And more...
```

**Note:** Setup will automatically index your project after configuration.

> **Agent-specific notes**
> - **OpenCode** is configured via its CLI (`opencode mcp add codenexus -- codenexus -w <project> serve`), which writes `~/.config/opencode/opencode.jsonc` (JSON5). CodeNexus reads this back automatically.
> - **Antigravity** has no `mcp add` CLI subcommand, so CodeNexus injects the server block into `~/.gemini/config/mcp_config.json` (or your workspace `.agents/mcp_config.json`). After applying, reload via `/mcp` in the Antigravity CLI/IDE.

### Register Multiple Repos with One Agent

Since one MCP registration can serve many indexes (see [Multiple Indexes per Agent](#multiple-indexes-per-agent)), the wizard lets you register several repos with a single agent in one step — no hand-editing of config. This is the convenient path to CodeNexus's token-saving multi-repo context.

**Non-interactive (scripts / CI):**

```bash
codenexus wizard setup-workspace claude \
  -w ~/work/my-workspace \
  --repo alpha=~/code/alpha \
  --repo beta=~/code/beta \
  --repo gamma=~/code/gamma
```

- `-w <root>` is the **workspace root** — a directory that will hold `.codenexus/workspace.json`. It is *not* one of the repos; pick any folder (often an empty one you keep for the workspace).
- `--repo ALIAS=PATH` is repeatable. The alias is how files from that repo show up in results (`alpha/src/app.py`). If you omit the `=PATH` form and pass just a path, the folder name is used as the alias.
- Every repo is indexed, and the agent config is written pointing at the workspace root — one registration serves all of them.

**Interactive:**

```bash
codenexus wizard interactive
```

The wizard offers a mode prompt: **1 = single repo** (the existing flow), **2 = multi-repo**. Choose `2`, then supply a workspace root and repeatable repo path/alias pairs (empty path to finish).

**Append more repos later:** re-run the same `setup-workspace` command with the same `-w` root and new `--repo` entries — existing members are kept, new ones are added.

### Independent Per-Project Indexes (Claude Code)

The federated `setup-workspace` above serves many repos through **one** MCP
registration — handy for cross-repo context, but the indexes share a serving
session. If you instead want **fully separate** indexes that load only inside a
given project (e.g. you have projects A and B and never want their context to
mix), register each one with the `--scope local` flag:

```bash
codenexus wizard setup claude --scope local --project ~/code/alpha
codenexus wizard setup claude --scope local --project ~/code/beta
```

- Each command writes a **local-scope** entry in `~/.claude.json` under
  `projects[<dir>].mcpServers.codenexus` → `codenexus -w <dir> serve`.
- The index for project A loads **only** when Claude Code runs inside `~/code/alpha`;
  project B's index loads only inside `~/code/beta`. They never share context.
- Other `projects` entries and unrelated keys in `~/.claude.json` are preserved;
  the file is backed up before each write.
- If a user-scope (global) `codenexus` entry already exists at the top-level
  `mcpServers`, the wizard warns — that global entry applies to every project
  and would shadow the per-project one, so remove it (e.g.
  `codenexus wizard clear` or edit the file) for the per-project indexes to take
  effect independently.

> Per-project local scope is **Claude Code-specific** (it relies on Claude Code's
> `projects` map in `~/.claude.json`). Other agents don't have an equivalent
> per-project mechanism wired here; for them, use the default `setup` (global)
> or the federated `setup-workspace`.

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
- [x] VS Code extension
- [ ] Function-level call-graph extraction beyond imports (in progress)
- [x] Multi-index serving: one agent registration, many indexes
- [x] Multi-repo registration in the wizard (`wizard setup-workspace` + interactive)

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

**Fully open source:** there are no tiers or activation keys. All seven
languages, session memory, local LLM support and unlimited multi-repo
workspaces are available to everyone.

### Multiple Indexes per Agent

One MCP registration can serve many indexes: point it at a **workspace root**
containing `.codenexus/workspace.json`.

The easiest way to build this is the wizard — see
[Register Multiple Repos with One Agent](#register-multiple-repos-with-one-agent).
For a manual/low-level flow, use the `workspace` commands:

```bash
# 1. Build a workspace (inside the root directory)
codenexus workspace init my-workspace
codenexus workspace add alpha C:/code/alpha
codenexus workspace add beta  C:/code/beta
codenexus workspace index

# 2. Register your agent against the WORKSPACE ROOT
#    args: ["-w", "<workspace-root>", "serve"]
```

Behavior once served this way:

| Tool | Multi-index behavior |
|------|----------------------|
| `run_pipeline` / `get_context_capsule` | Search every member repo; results merged and ranked by centrality |
| `index_status` | Reports `mode: "multi-repo"` plus a per-repo breakdown |
| `get_skeleton` | Accepts aliased paths (`alpha/src/app.py`) |
| `impact`-style queries | Run within the owning repo |

Only indexed members participate; register more anytime with
`codenexus workspace add`, re-run `codenexus workspace index`, and restart
the MCP server.

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

<!-- Korean documentation follows -->
<a id="korean"></a>

---

# CodeNexus AI — 한국어 문서

**AI 코딩 에이전트를 위한 컨텍스트 엔진**

[English](#what-is-codenexus) | **한국어**

---

## CodeNexus란?

CodeNexus는 **로컬 우선 컨텍스트 엔진**으로, AI 코딩 에이전트가 코드베이스를 더 잘 이해하도록 돕습니다. 코드의 실시간 의존성 그래프를 구축하고, AI 에이전트에 관련된 컨텍스트만 제공하여 토큰 사용량을 **최대 약 99%**(실측값) 절감하면서 코드 품질을 향상시킵니다.

### 주요 기능

- **로컬 우선**: 코드가 기계를 벗어나지 않음
- **토큰 절감**: AI 컨텍스트 토큰을 최대 약 99%까지 감축 (실측정: 211개 파일 프로젝트에서 작업당 951K → 약 4.3K)
- **멀티 언어**: Python, JavaScript, TypeScript, Go, Rust, Java, C# (7개 언어)
- **MCP 호환**: 공식 `mcp` Python SDK 기반 (표준 `Content-Length` 프레임 stdio). Hermes, Claude Code, Cursor, Windsurf, Zed, Continue.dev, GitHub Copilot, Codex, Augment, OpenCode, Antigravity 및 모든 spec 준수 MCP 클라이언트와 연동
- **빠른 인덱싱**: SQLite 기반 의존성 그래프
- **PageRank**: 중요도 기반 스마트 랭킹 (import 그래프 기반, 실노드 간 엣지)

---

## 빠른 시작

### 설치

```bash
pip install codenexus-ai
```

**소스에서 개발하는 경우(로컬 수정 시 권장):** 저장소 내용이 바로 반영되도록
editable 모드로 설치하세요. 일반 `pip install .`은 코드를 `site-packages`로
복사하므로, 이후 파일을 수정해도 이전 복사본이 실행됩니다.

```bash
git clone https://github.com/uptodatelabs/CodeNexus.git
cd CodeNexus
pip install -e .
```

### 기본 사용법

```bash
# 프로젝트 인덱싱
codenexus index

# 컨텍스트 검색
codenexus search "인증 미들웨어"

# 컨텍스트 파이프라인 실행
codenexus pipeline "로그인 버그 수정"

# 상태 확인
codenexus status

# 상위 노드 보기
codenexus top

# 임팩트 분석
codenexus impact "main"
```

---

## 작동 방식

```
코드베이스
     ↓
[CodeNexus 인덱서]
     ↓
┌─────────────────────────────────────┐
│  의존성 그래프 (SQLite + FTS5)      │
│  - 함수, 클래스, 임포트             │
│  - 호출 관계                        │
│  - 타입 정보                        │
│  - PageRank 중앙성                  │
└─────────────────────────────────────┘
     ↓
[컨텍스트 캡슐 생성기]
     ↓
┌─────────────────────────────────────┐
│  AI 에이전트를 위한 최적화된 컨텍스트│
│  - 피봇 파일: 전체 소스             │
│  - 지원 파일: 스켈리톤만            │
│  - 토큰 예산: 준수                  │
└─────────────────────────────────────┘
     ↓
AI 에이전트 (Claude Code, Cursor 등)
```

---

## Claude Code 연동

CodeNexus는 Claude Code와 연동하여 AI 코딩 에이전트의 토큰 사용량을 줄입니다.

### 설정 방법

#### 1. CodeNexus 설치

```bash
pip install codenexus-ai
```

#### 2. `.claude.json` 파일 편집

**파일 위치:**
- macOS/Linux: `~/.claude.json`
- Windows: `C:\Users\사용자이름\.claude.json`

#### 3. 설정 추가

`~/.claude.json` 파일에 다음 내용을 추가하세요:

```json
{
  "mcpServers": {
    "codenexus": {
      "command": "codenexus",
      "args": ["-w", "여기에_프로젝트_경로", "serve"]
    }
  }
}
```

**⚠️ 중요: `여기에_프로젝트_경로`는 CodeNexus를 사용할 프로젝트의 경로입니다.**

### 경로 설정 예시

**❌ 잘못된 예시:**
```json
"args": ["-w", "C:\\Users\\username\\.codenexus", "serve"]
```
→ CodeNexus 설정 디렉토리 (오류)

**✅ 올바른 예시:**
```json
"args": ["-w", "C:\\Users\\username\\projects\\my-app", "serve"]
```
→ CodeNexus를 사용할 프로젝트 디렉토리

### OS별 경로 예시

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

### 여러 프로젝트 설정

여러 프로젝트에서 CodeNexus를 사용하려면, 각 프로젝트별로 설정을 추가하세요:

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

### 설정 확인

1. `.claude.json` 파일 저장
2. Claude Code 재시작
3. CodeNexus를 사용할 프로젝트 디렉토리에서 Claude 실행

```bash
cd C:\Users\username\projects\my-app
claude
```

### 문제 해결

**MCP 서버가 연결되지 않는 경우:**

CodeNexus는 **표준 MCP stdio 프로토콜**(공식 `mcp` Python SDK 기반, `Content-Length` 프레임 JSON-RPC)을 사용하므로, spec을 준수하는 모든 클라이언트(Hermes, Claude Code, Cursor, Windsurf, Zed, Continue.dev, GitHub Copilot, Codex, Augment)와 즉시 연결됩니다.

1. CodeNexus가 설치되어 있는지 확인:
   ```bash
   pip show codenexus-ai
   ```

2. 코드 실행 테스트:
   ```bash
   codenexus --version
   ```

3. 경로가 올바른지 확인 (따옴표 주의)

---

## 지원 언어

| 언어 | 상태 |
|------|------|
| Python | ✅ 완전 지원 |
| JavaScript | ✅ 완전 지원 |
| TypeScript | ✅ 완전 지원 |
| Go | ✅ 완전 지원 |
| Rust | ✅ 완전 지원 |
| Java | ✅ 완전 지원 |
| C# | ✅ 완전 지원 |

> AST 정밀 인덱싱을 위해 파싱 extras 설치를 권장합니다:
> `pip install "codenexus-ai[full]"`. 없으면 내장 regex 스캐너로 폴백합니다.
> import 그래프 해석·PageRank 랭킹·임팩트 분석은 두 모드 모두에서 동작합니다.

---

## 지원 AI 에이전트

CodeNexus는 MCP(MCP 미지원 에이전트는 스킬)로 AI 코딩 에이전트와 연동됩니다.
설정 마법사가 설치된 에이전트를 자동 감지하고 각각 올바른 설정 형식을 기록합니다.

| 에이전트 | 설정 파일 | MCP 키 |
|-------|-------------|---------|
| Claude Code | `~/.claude.json` | `mcpServers` |
| Cursor | `~/.cursor/mcp.json` | `mcpServers` |
| Windsurf | `~/.windsurf/mcp.json` | `mcpServers` |
| GitHub Copilot | `~/.copilot/mcp-config.json` | `mcpServers` |
| Zed | `~/.zed/settings.json` | `mcpServers` |
| Continue.dev | `~/.continue/config.json` | `mcpServers` |
| Augment | `~/.augment/settings.json` | `mcpServers` |
| OpenCode | `~/.config/opencode/opencode.jsonc` | `mcp` |
| Antigravity | `~/.gemini/config/mcp_config.json` | `mcpServers` |
| Hermes Agent | `~/.hermes/config.yaml` | `mcp_servers` |
| Codex | `~/.codex/config.toml` | `mcp_servers` |
| OpenClaw | `~/.openclaw/workspace/skills/codenexus/SKILL.md` | skill |

---

## 다른 AI 에이전트 연동

### OpenClaw 연동

[OpenClaw](https://github.com/openclaw/openclaw)는 WhatsApp, Telegram, Slack, Discord 등과 연결되는 개인 AI 어시스턴트입니다.

#### 설정 방법

OpenClaw는 MCP를 직접 지원하지 않습니다. 스킬 시스템을 통해 CLI 명령어를 사용합니다.

**1. CodeNexus 설치:**

```bash
pip install codenexus-ai
```

**2. OpenClaw 스킬 생성:**

`~/.openclaw/workspace/skills/codenexus/SKILL.md` 파일 생성:

```markdown
---
name: codenexus
description: CodeNexus로 코드 검색 및 분석
allowed_tools:
  - bash
---

# CodeNexus 스킬

CodeNexus를 사용하여 워크스페이스의 코드를 검색하고 분석합니다.

## 명령어

- `codenexus index` - 워크스페이스 인덱싱
- `codenexus search "query"` - 코드 검색
- `codenexus pipeline "task"` - 태스크용 컨텍스트 생성
```

**3. OpenClaw에서 사용:**

```
/codenexus search "인증 미들웨어"
/codenexus pipeline "로그인 버그 수정"
```

### Hermes Agent 연동

[Hermes Agent](https://github.com/NousResearch/hermes-agent)는 Nous Research의 자기 개선 AI 에이전트입니다.

#### 설정 방법

Hermes는 MCP 서버를 지원합니다. CodeNexus를 MCP 서버로 설정하세요.

**1. CodeNexus 설치:**

```bash
pip install codenexus-ai
```

**2. MCP 서버 추가:**

```bash
hermes mcp add codenexus -- codenexus -w /path/to/your/project serve
```

또는 `~/.hermes/config.yaml`에 추가:

```yaml
mcp_servers:
  codenexus:
    command: codenexus
    args:
      - serve
      - -w
      - /path/to/your/project
```

**3. Hermes에서 사용:**

```
/hermes search "인증 미들웨어"
/hermes pipeline "로그인 버그 수정"
```

### OpenCode 연동

[OpenCode](https://opencode.ai/)는 오픈 소스 AI 코딩 에이전트입니다. CodeNexus는 CLI와 바로 연결됩니다.

**1. CodeNexus 설치:**
```bash
pip install codenexus-ai
```

**2. MCP 서버 추가 (`~/.config/opencode/opencode.jsonc` 자동 구성):**
```bash
opencode mcp add codenexus -- codenexus -w /path/to/your/project serve
```

마법사 사용:
```bash
codenexus wizard setup opencode
```

**3. 확인:**
```bash
opencode mcp list
# → ✓ codenexus connected
```

### Antigravity 연동

[Antigravity](https://antigravity.google/)(구글 에이전틱 IDE/CLI, `agy`)는 설정 파일을 통해 MCP를 지원합니다. `mcp add` 하위 명령이 없으므로 설정에 서버 블록을 주입합니다.

**1. CodeNexus 설치:**
```bash
pip install codenexus-ai
```

**2. 마법사로 적용 (`~/.gemini/config/mcp_config.json` 기록):**
```bash
codenexus wizard setup antigravity
```

또는 `~/.gemini/config/mcp_config.json`(또는 워크스페이스 `.agents/mcp_config.json`)에 직접 추가:
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

**3. Antigravity CLI/IDE에서 `/mcp`로 리로드** 후 `run_pipeline` / `get_context_capsule` 도구를 통해 CodeNexus를 사용합니다.

### 다른 에이전트

CLI 명령어를 지원하는 모든 에이전트에서 사용 가능:

```bash
# 직접 CLI 사용
codenexus index
codenexus search "query"
codenexus pipeline "task"
codenexus status

# 프로그래밍 방식 사용을 위한 JSON 출력
codenexus search "query" --json
```

`pipeline` 명령은 원시 JSON 대신 **사람이 읽는 컨텍스트 캡슐**(작업, 감지된
의도, 토큰 추정, 피봇 파일 패널, 스켈리톤 트리)을 출력합니다. 프로그래밍
클라이언트(MCP 에이전트)는 `run_pipeline` 도구로 동일 데이터를 구조화된 JSON으로
받습니다.

---

## 토큰 절감 예시

`openclaw_workspace/projects` 인덱스 기준 측정 (211개 파일, 4,224개 노드, 62,194개 엣지):

**전체 코드베이스를 모델에 전송할 때:**
```
951,322 토큰 (전체 소스: Python + JS/TS)
```

**작업별로 CodeNexus에 컨텍스트 요청할 때** (`run_pipeline`, 실제 작업 5개 평균):
```
작업당 ~4,325 토큰
```

**절감율: 약 99.5%** — 작업과 관련된 파일/정의만 반환됩니다.

> 정확한 수치는 프로젝트 크기와 작업 범위에 따라 다릅니다. CodeNexus는 항상 전체 트리가 아닌 *관련된* 일부만 반환합니다.

---

## 설정 마법사

CodeNexus는 AI 코딩 에이전트를 쉽게 설정할 수 있는 마법사를 포함하고 있습니다.

### 설치된 에이전트 감지

```bash
codenexus wizard detect
```

### 지원되는 에이전트 목록

```bash
codenexus wizard list
```

### 특정 에이전트 설정

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

# OpenCode (오픈 소스 CLI)
codenexus wizard setup opencode

# Antigravity (구글 에이전틱 IDE/CLI — `agy`)
codenexus wizard setup antigravity

# 그 외...
```

**참고:** 설정 후 자동으로 프로젝트를 인덱싱합니다.

> **에이전트별 참고 사항**
> - **OpenCode**는 CLI로 구성합니다(`opencode mcp add codenexus -- codenexus -w <project> serve`) — `~/.config/opencode/opencode.jsonc`(JSON5)에 기록되며 CodeNexus가 자동으로 읽어 들입니다.
> - **Antigravity**는 `mcp add` 하위 명령이 없으므로 CodeNexus가 `~/.gemini/config/mcp_config.json`(또는 워크스페이스 `.agents/mcp_config.json`)에 서버 블록을 주입합니다. 적용 후 Antigravity에서 `/mcp`로 리로드하세요.

### 하나의 에이전트에 여러 레포 등록

MCP 등록 하나로 여러 인덱스를 서빙하므로([에이전트별 멀티 인덱스](#에이전트별-멀티-인덱스) 참고), 마법사를 통해 여러 레포를 한 번에 등록할 수 있습니다 — 설정 파일을 직접 편집할 필요 없습니다. 토큰 절감 멀티-repo 컨텍스트로 가는 가장 편리한 경로입니다.

**비대화형 (스크립트 / CI):**

```bash
codenexus wizard setup-workspace claude \
  -w ~/work/my-workspace \
  --repo alpha=~/code/alpha \
  --repo beta=~/code/beta \
  --repo gamma=~/code/gamma
```

- `-w <루트>`는 **워크스페이스 루트** — `.codenexus/workspace.json`이 저장될 디렉토리입니다. 레포 중 하나가 아니며, 보통 워크스페이스용으로 비워둔 빈 폴더를 지정하면 됩니다.
- `--repo ALIAS=PATH`는 반복 가능합니다. 별칭은 결과에서 해당 레포 파일이 표시되는 방식(`alpha/src/app.py`)입니다. `=PATH` 형태를 생략하고 경로만 넘기면 폴더명이 별칭으로 쓰입니다.
- 모든 레포가 인덱싱되며, 에이전트 설정은 워크스페이스 루트를 가리키도록 기록됩니다 — 등록 하나가 전부를 서빙합니다.

**대화형:**

```bash
codenexus wizard interactive
```

마법사가 모드 프롬프트를 제공합니다: **1 = 단일 레포**(기존 흐름), **2 = 멀티-repo**. `2`를 선택한 뒤 워크스페이스 루트와 반복 가능한 레포 경로/별칭 쌍을 입력합니다(빈 경로로 종료).

**나중에 레포 추가:** 동일한 `-w` 루트로 같은 `setup-workspace` 명령을 새 `--repo` 항목과 함께 다시 실행하면 — 기존 멤버는 유지되고 새 레포만 추가됩니다.

### 프로젝트별 독립 인덱스 (Claude Code)

위의 `setup-workspace` 연동 방식은 **하나의** MCP 등록으로 여러 레포를 서빙합니다 — 레포 간 문맥을 함께 쓸 수 있어 편리하지만, 인덱스가 하나의 서빙 세션을 공유합니다. 반면 프로젝트별로 **완전히 분리된** 인덱스, 즉 해당 프로젝트 안에서 Claude Code를 실행할 때만 로드되는 인덱스를 원한다면(예: A, B 프로젝트가 있고 문맥이 섞이는 것을 원치 않을 때) `--scope local` 플래그로 각각 등록합니다:

```bash
codenexus wizard setup claude --scope local --project ~/code/alpha
codenexus wizard setup claude --scope local --project ~/code/beta
```

- 각 명령은 `~/.claude.json`의 `projects[<dir>].mcpServers.codenexus` →
  `codenexus -w <dir> serve`에 **로컬 스코프** 항목을 작성합니다.
- 프로젝트 A의 인덱스는 Claude Code가 `~/code/alpha` 안에서 실행될 때 **만**
  로드되고, 프로젝트 B의 인덱스는 `~/code/beta` 안에서만 로드됩니다. 문맥이
  섞이지 않습니다.
- `~/.claude.json`의 다른 `projects` 항목과 관련 없는 키는 보존되며, 쓰기 전에
  파일이 백업됩니다.
- 최상위 `mcpServers`에 사용자 스코프(전역) `codenexus` 항목이 이미 있으면
  마법사가 경고합니다 — 전역 항목은 모든 프로젝트에 적용되어 프로젝트별
  항목을 가리므로, 프로젝트별 인덱스가 독립적으로 동작하려면
  `codenexus wizard clear` 또는 파일 직접 수정으로 제거하세요.

> 프로젝트별 로컬 스코프는 **Claude Code 전용**입니다(`~/.claude.json`의
> `projects` 맵에 의존). 다른 에이전트는 여기서 연결한 동등한 프로젝트별
> 메커니즘이 없으므로, 기본 `setup`(전역) 또는 연동 `setup-workspace`를
> 사용하세요.

### 인덱스 삭제

```bash
codenexus wizard clear
```

인덱스 디렉토리를 표시하고, 선택적으로 삭제할 수 있습니다.

스크립트/CI 등 비대화형 환경에서는 프롬프트 없이 전체 삭제:

```bash
codenexus wizard clear --all --yes
```

- `--all`: 발견된 모든 인덱스 선택
- `--yes`: 확인 프롬프트 생략

ID 지정 삭제(`idx-1,idx-3` 입력)나 프로젝트 디렉토리명 입력으로 개별 확인 삭제도 가능합니다.

### 대화형 설정

```bash
codenexus wizard interactive
```

---

## CLI 명령어

| 명령어 | 설명 |
|--------|------|
| `codenexus index` | 워크스페이스 인덱싱 |
| `codenexus search <query>` | 컨텍스트 검색 (`--json` 지원) |
| `codenexus pipeline <task>` | 컨텍스트 파이프라인 실행 |
| `codenexus status` | 인덱스 상태 확인 (`--json` 지원) |
| `codenexus top` | 중앙성 상위 노드 보기 |
| `codenexus impact <symbol>` | 임팩트 분석 |
| `codenexus serve` | MCP 서버 시작 |
| `codenexus clear` | 인덱스 데이터 삭제 |

---

## 로드맵

- [x] 기본 의존성 그래프
- [x] PageRank 중앙성 (import 그래프 기반, 실노드 간 엣지)
- [x] 병렬 인덱싱
- [x] 증분 인덱싱
- [x] Tree-sitter 통합 (`pip install "codenexus-ai[full]"`)
- [x] 로컬 LLM 지원
- [x] 멀티 레포 워크스페이스
- [x] VS Code 확장
- [ ] 함수 수준 콜그래프 추출 확대 (진행 중)
- [x] 멀티 인덱스 서빙: 에이전트 등록 하나로 여러 인덱스
- [x] 마법사 멀티-repo 등록 (`wizard setup-workspace` + 대화형)

---

## 기여하기

기여를 환영합니다! Pull Request를 제출해주세요.

1. Fork 하기
2. 피처 브랜치 만들기 (`git checkout -b feature/amazing-feature`)
3. 커밋하기 (`git commit -m 'Amazing feature 추가'`)
4. 푸시하기 (`git push origin feature/amazing-feature`)
5. Pull Request 열기

---

## 라이선스

이 프로젝트는 MIT 라이선스로 제공됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

**완전 오픈소스:** 티어나 활성화 키가 없습니다. 7개 언어 전체, 세션 메모리,
로컬 LLM, 무제한 멀티레포 워크스페이스를 모두에게 제공합니다.

### 에이전트별 멀티 인덱스

MCP 등록 하나로 여러 인덱스를 사용할 수 있습니다. `.codenexus/workspace.json`이
있는 **워크스페이스 루트**를 바라보게 하세요.

가장 쉬운 구성 방법은 마법사입니다 — [하나의 에이전트에 여러 레포 등록](#하나의-에이전트에-여러-레포-등록)을
참고하세요. 수동/저수준 흐름은 `workspace` 명령을 사용합니다:

```bash
# 1. 워크스페이스 구성 (루트 디렉토리에서)
codenexus workspace init my-workspace
codenexus workspace add alpha C:/code/alpha
codenexus workspace add beta  C:/code/beta
codenexus workspace index

# 2. 에이전트를 워크스페이스 루트에 등록
#    args: ["-w", "<워크스페이스-루트>", "serve"]
```

이렇게 서빙하면:

| 도구 | 멀티 인덱스 동작 |
|------|------------------|
| `run_pipeline` / `get_context_capsule` | 모든 멤버 레포를 검색, 중앙성 순으로 병합 반환 |
| `index_status` | `mode: "multi-repo"` 및 레포별 통계 보고 |
| `get_skeleton` | 별칭 경로(`alpha/src/app.py`) 지원 |
| 임팩트 조회 | 해당 노드가 속한 레포 내부에서 수행 |

인덱싱된 멤버만 참여합니다. `codenexus workspace add`로 추가하고
`codenexus workspace index` 재실행 후 MCP 서버를 재시작하면 됩니다.

---

## 감사의 말

- [vexp](https://vexp.dev/)에서 영감을 받음
- Python, SQLite, MCP로 구축
- 모든 기여자에게 감사

---

## 지원

CodeNexus가 유용하다면 프로젝트 지원을 고려해주세요:

[![Ko-fi](https://img.shields.io/badge/Ko--fi-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/uptodatelabs)
[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-CodeNexus-ea4aaa?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/uptodatelabs)

---

**코드를 연결하세요. AI를 강화하세요.**
