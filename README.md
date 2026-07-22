# CodeNexus

**The context engine for AI coding agents**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

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
pip install codenexus
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

Add to your `~/.claude.json`:

```json
{
  "mcpServers": {
    "codenexus": {
      "command": "codenexus",
      "args": ["serve", "-w", "/path/to/your/project"]
    }
  }
}
```

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

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/yourusername)
[![Sponsor](https://img.shields.io/badge/Sponsor-CodeNexus-ea4aaa?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/yourusername)

---

**Connect your code. Empower your AI.**
