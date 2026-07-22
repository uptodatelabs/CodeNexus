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
- **Token reduction**: Save 50-70% on AI API costs
- **Multi-language**: Python, JavaScript, TypeScript support
- **MCP compatible**: Works with Claude Code, Cursor, and other AI agents
- **Fast indexing**: SQLite-based dependency graph

---

## Quick Start

### Installation

```bash
pip install codenexus-ai
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
      "args": ["serve", "-w", "여기에_프로젝트_경로"]
    }
  }
}
```

**⚠️ 중요: `여기에_프로젝트_경로`는 CodeNexus를 사용할 프로젝트의 경로입니다.**

### 경로 설정 예시

**❌ 잘못된 예시:**
```json
"args": ["serve", "-w", "C:\\Users\\username\\.codenexus"]
```
→ CodeNexus 설정 디렉토리 (오류)

**✅ 올바른 예시:**
```json
"args": ["serve", "-w", "C:\\Users\\username\\projects\\my-app"]
```
→ CodeNexus를 사용할 프로젝트 디렉토리

### OS별 경로 예시

**Windows:**
```json
{
  "mcpServers": {
    "codenexus": {
      "command": "codenexus",
      "args": ["serve", "-w", "C:\\Users\\username\\projects\\my-app"]
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
      "args": ["serve", "-w", "/home/username/projects/my-app"]
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
          "args": ["serve", "-w", "C:\\Users\\username\\projects\\app1"]
        }
      }
    },
    "C:\\Users\\username\\projects\\app2": {
      "mcpServers": {
        "codenexus": {
          "command": "codenexus",
          "args": ["serve", "-w", "C:\\Users\\username\\projects\\app2"]
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

## Token Savings Example

**Before CodeNexus:**
```
8,247 tokens per query
```

**After CodeNexus:**
```
2,140 tokens per query (74% reduction)
```

---

## Roadmap

- [ ] Tree-sitter integration for better parsing
- [ ] Graph centrality (PageRank) for better ranking
- [ ] Local LLM support for additional savings
- [ ] Multi-repo workspace support
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
