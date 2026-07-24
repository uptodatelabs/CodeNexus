# Changelog

All notable changes to CodeNexus will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.22] - 2026-07-25

### Fixed
- **GitHub Copilot integration bug.** `AgentType.COPILOT.config_file` pointed at `~/.github/copilot-instructions.md`. The wizard's `_apply_mcp_config` then tried to parse that markdown file as JSON and overwrote it with MCP content, destroying the user's Copilot instructions. Changed the path to the real Copilot CLI MCP config (`~/.copilot/mcp-config.json`) and added a guard in `_apply_mcp_config` that refuses to write any unsupported config format (anything other than `.json`/`.yaml`/`.yml`/`.toml`), printing a manual-setup hint instead of clobbering the file.

### Added
- Tests covering every supported agent's MCP config key and `apply_config` file write (`test_agent_mcp_config_keys`, `test_apply_mcp_config_writes_file`, `test_apply_mcp_config_skips_unsupported_format`).
- Documented all 10 supported agents (config file + MCP key) and `wizard clear --all --yes` in README.

## [1.1.21] - 2026-07-24

### Fixed
- **Critical crash in `wizard clear` (TypeError: object of type 'int' has no len()).** The `wizard list` command was defined as `def list():`, which shadowed the builtin `list` at module scope. `clear` then called the click `list` Command instead of the builtin, triggering infinite recursion and the crash. Renamed the command function to `list_cmd` (kept the `list` subcommand name). Also added `--all`/`--yes` non-interactive flags.

## [1.1.20] - 2026-07-24

### Fixed
- CI: fixed 77 ruff lint errors (`List`/`Dict` → builtin generics, unused variable) so the `Tests` workflow passes. No runtime behavior change.

## [1.1.19] - 2026-07-24

### Changed
- Bumped version to 1.1.19.

### Docs
- Documented that local development must use `pip install -e .` (editable). A non-editable `pip install .` copies the code into `site-packages` and silently keeps running the stale copy even after repo edits — which previously made `wizard clear` appear location-dependent (it only saw the cwd's `.codenexus`).

## [1.1.18] - 2026-07-24

### Fixed
- **Impact/PageRank was always 0 (critical bug).** `DependencyGraph` built nodes from `SELECT *` rows with `Node(*row[:9])`, but the `nodes` table has `created_at` as the 10th column, so the `centrality_score` column was silently dropped from the `Node` object. Added `Node.from_row()` and replaced all `Node(*row)` call sites so centrality scores are now loaded correctly.
- **Call-edge extraction added.** The parser now extracts caller→callee edges from function calls (tree-sitter call nodes and a regex fallback), so the dependency graph forms real call chains and PageRank reflects actual code structure. Cross-file calls resolve to shared global symbol nodes.
- **Fixed SQLite cross-thread race in indexing.** Parallel parsing wrote to the shared SQLite connection from worker threads; DB writes are now buffered and applied sequentially on the main thread before `compute_pagerank()` runs.
- **README `-w` flag position corrected.** Every MCP config example used `["serve", "-w", ...]` which produces the invalid command `codenexus serve -w ...`. Correct order is `["-w", "<path>", "serve"]` (matching `wizard`). Fixed in `README.md`, `README.ko.md`, and the `hermes mcp add` snippet.
- **Version numbers unified.** `__init__.py` (1.0.0), `cli.py` (1.1.18), and `mcp_server.py` (1.1.18) now all match `pyproject.toml` (1.1.18).

## [1.1.6] - 2026-07-24

### Fixed
- `wizard clear` now actually parses each AI agent's config (Claude Code, Hermes, Cursor, Codex, ...) via `agent_parser` to discover CodeNexus-wired projects, instead of only scanning `~/ .codenexus` and home subdirs
- `wizard clear` only lists projects that have a real index on disk (`find_codenexus_index`)
- Hardened deletion safety: unique `idx-N` ids, `--dry-run` flag, and path-based confirmation (must type the exact project directory name to delete)

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
