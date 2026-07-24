# Changelog

All notable changes to CodeNexus will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.3] - 2026-07-24

### Fixed
- Fixed agent detection logic to stop at home directory
- Prevents false positives when checking parent directories

## [1.1.2] - 2026-07-24

### Fixed
- Improved agent detection to check parent directories
- OpenClaw now detected when ~/.openclaw exists

## [1.1.1] - 2026-07-24

### Fixed
- Fixed CLI version to match pyproject.toml (was hardcoded as 0.1.0)

## [1.1.0] - 2026-07-24

### Added
- Agent Setup Wizard with interactive configuration
- Support for 10 AI coding agents:
  - Claude Code (MCP)
  - OpenClaw (Skill system)
  - Hermes Agent (MCP)
  - Cursor (MCP)
  - Windsurf (MCP)
  - GitHub Copilot (MCP via copilot-mcp-server)
  - Codex (MCP)
  - Zed (MCP)
  - Continue.dev (MCP)
  - Augment (MCP via Auggie CLI)
- Auto-detect installed agents
- Setup guides for each agent

### Fixed
- Resolved all ruff lint errors
- Fixed whitespace issues
- Removed unused variables

## [1.0.3] - 2026-07-22

### Fixed
- Resolved all ruff lint errors (21 errors fixed)
- Fixed whitespace issues (W291, W293)
- Removed unused variables (F841)
- Fixed bare except statements (E722)
- Updated imports to avoid unused import warnings (F401)
- All 12 tests passing

## [1.0.2] - 2026-07-22

### Fixed
- Auto-fixed 518 lint issues (whitespace, imports, formatting)
- Improved code quality and consistency
- Updated package name to codenexus-ai
- Updated all repository URLs to uptodatelabs

## [1.0.0] - 2026-07-22

### Added
- Initial stable release
- Dependency graph with PageRank centrality scoring
- Code parsing for 9 languages (Python, JavaScript, TypeScript, Go, Rust, Java, C#, PHP, Ruby)
- Tree-sitter integration with regex fallback
- FTS5 full-text search
- Parallel and incremental indexing
- MCP server for AI agent integration
- Local LLM support via llama-cpp-python
- Intent detection (explore/debug/modify/refactor)
- Context compression
- Multi-repo workspace support
- Cross-repo search and dependency detection
- VS Code extension with sidebar and CodeLens
- Session memory and decision tracking
- Auto-generated session summaries
- CLI with comprehensive commands

### Features
- **Graph Engine**: SQLite-based dependency graph with PageRank
- **Parser**: 9 language support with tree-sitter/regex fallback
- **Server**: MCP protocol for AI agent integration
- **LLM**: Local model support for enhanced context
- **Workspace**: Multi-repo management and cross-repo search
- **Memory**: Session tracking and decision logging
- **VS Code**: Extension with sidebar, CodeLens, auto-indexing

### CLI Commands
- `codenexus index` - Index workspace
- `codenexus search` - Search for context
- `codenexus pipeline` - Run context pipeline
- `codenexus status` - Show index status
- `codenexus top` - Show top nodes by centrality
- `codenexus impact` - Analyze impact
- `codenexus serve` - Start MCP server
- `codenexus clear` - Clear index
- `codenexus llm` - LLM commands
- `codenexus workspace` - Multi-repo commands
- `codenexus memory` - Session memory commands

## [0.1.0] - 2026-07-22

### Added
- Initial development release
- Basic dependency graph
- Python, JavaScript, TypeScript parsing
- MCP server
- CLI interface
