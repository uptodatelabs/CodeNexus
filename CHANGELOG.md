# Changelog

All notable changes to CodeNexus will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-08-26

### Fixed — critical
- **PageRank / impact analysis actually work now**: import edges previously
  pointed from a `{path}::import` pseudo-node to raw statement text, so no
  edge ever connected two real nodes; centrality was uniform and impact
  queries always empty. A new resolver (`codenexus/resolver.py`) gives every
  file a module node and rewrites imports into real module/symbol edges
  (Python relative/absolute, JS/TS relative requires, Go stems, Rust crate
  paths, Java/C# dotted names); unresolvable external imports are dropped.
- **Node rows mapped by keyword, not position**: DB-loaded nodes had
  `centrality_score` land in `dependencies` (float) leaving scores at 0.0,
  destroying all Python-side ranking.
- **MCP stdio protocol compliance**: `notifications/initialized` is no longer
  mis-matched as `initialized` (which emitted stray `null` lines and illegal
  error replies to notifications); protocol version negotiation added; tool
  failures use the MCP `isError` convention; required arguments validated
  (-32602) instead of silently coerced to empty strings.
- **wizard setup can no longer destroy agent configs**: an existing config
  file that fails to read aborts the merge instead of overwriting it with
  near-empty content; writes are atomic with `.codenexus-backup` backups.

### Fixed — correctness & safety
- `wizard list` callback shadowed builtin `list`, crashing
  `workspace search -r` and `memory decide` at runtime
- Re-indexing duplicated every edge row (unique index + dedupe migration);
  FTS5 external-content table now kept in sync via triggers + rebuild
  migration (ghost search hits gone)
- tree-sitter byte offsets were sliced against str: sources with CJK or any
  multi-byte characters corrupted names/signatures; UTF-8 BOM broke first-
  line parsing; regex fallback fixed for Rust enums, Java/C# constructors,
  Go grouped imports, brace-language block extents
- Thread safety: graph and memory connections locked; incremental cache is
  versioned; deleted files purge their nodes/edges; failed parses are no
  longer cached as indexed; full re-index clears stale rows
- workspace.json load failure refuses destructive saves; alias validation;
  search opens all registered repos after restart; status no longer creates
  empty .db side effects
- Session ids gain random suffix (same-second collisions crashed); unknown
  stored decision types degrade gracefully instead of crashing reads;
  memory searches bounded with LIMIT + LIKE escaping
- License: malformed tier keys return False instead of crashing;
  has_feature strictly boolean; enforcement actually wired (free tier node
  budget in indexer, repo-count cap in workspaces)

### Added
- `codenexus search --json` and `codenexus status --json` (documented,
  consumed by the VS Code extension)
- Shared pipeline module: both MCP server implementations run identical
  capsule logic; presets (explore/debug/modify) tune result width
- CI workflow (ruff + pytest on ubuntu/windows, Python 3.10-3.12); releases
  now gated on tests passing before PyPI publish
- 30-case regression suite covering every fix above (42 tests total)
- VS Code extension: safe argument quoting (command-injection hardening),
  debounced auto reindex on save, workspace-relative result paths resolved

- `wizard clear` now actually parses each AI agent's config (Claude Code, Hermes, Cursor, Codex, ...) via `agent_parser` to discover CodeNexus-wired projects, instead of only scanning `~/ .codenexus` and home subdirs
- `wizard clear` only lists projects that have a real index on disk (`find_codenexus_index`)
- Hardened deletion safety: unique `idx-N` ids, `--dry-run` flag, and path-based confirmation (must type the exact project directory name to delete)

### Changed
- tomli-w/tomli declared as real dependencies; wizard no longer runs
  `pip install` at runtime
- Version single-sourced in `codenexus/_version.py`; CLI/MCP serverInfo/
  pyproject aligned at 1.2.0
- Library diagnostics routed through logging instead of stdout

## [1.1.5] - 2026-07-24

### Added
- OpenClaw openclaw.json parsing for accurate workspace/agent detection
- Dynamic workspace and skills path discovery from config
- Agent allowlist support

### Fixed
- Improved OpenClaw detection accuracy
- Proper skill path resolution based on config priority

## [1.1.4] - 2026-07-24

### Added
- Dynamic OpenClaw path detection with environment variable support
- OPENCLAW_HOME and OPENCLAW_CONFIG environment variables
- Multiple fallback paths for OpenClaw detection

### Fixed
- Agent detection now properly stops at home directory
- Interactive wizard now applies configuration automatically

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
