## [1.2.2] - 2026-08-26

### Fixed — indexing crash on real codebases
- Call edges referencing symbols without a node (builtins, stdlib, typos,
  cross-file targets) raised FOREIGN KEY constraint failed and aborted
  `codenexus index` entirely. Endpoints are now validated at insert time in
  both indexers; unresolved calls are dropped instead of crashing (red→green
  regression test included).
- Method calls via attribute access (`self.validate()`, Python `attribute`
  nodes) were silently skipped by callee extraction; they now resolve to the
  method name so same-file call edges connect.

## [1.2.0] - 2026-08-26

### Fixed
- Import edges now resolve to real module/symbol nodes (resolver.py):
  PageRank, impact and dependents queries operate on a connected graph;
  pseudo `::import` edges are filtered before insert
- Graph hardening: thread locks, FTS5 trigger sync + rebuild migration,
  unique-edge dedupe migration, deleted-file purge on incremental index
- tree-sitter pinned <0.22 (0.23+ silently broke grammar loading, degrading
  installs to regex mode); parser slices spans from bytes so CJK sources no
  longer corrupt names/signatures; BOM stripped; regex fallback captures
  Rust enums, skips Java/C# constructors shadowing class ids
- Hermes config parsing survives Windows paths in double-quoted YAML;
  agent configs read as explicit UTF-8 (cp949 crash)
- wizard setup aborts instead of overwriting unreadable agent configs;
  memory decision ids collision-proof; license checks strictly boolean with
  real tier enforcement
- `wizard clear` listing rendered as plain-text blocks (rich panels dropped
  content on cp949 consoles and wrapped long paths)
- dispatch raises for unknown tools; cli search/status --json flags

# Changelog

All notable changes to CodeNexus will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.36] - 2026-07-27

### Fixed
- **wizard interactive writes to the paths agents actually read.** Two path-mismatch bugs made "wizard interactive sets 5 agents but clear shows them split/missing":
  - OpenCode `config_file` was `~/.opencode/opencode.jsonc` (a path OpenCode never reads). OpenCode uses the XDG path `~/.config/opencode/opencode.jsonc`. wizard wrote there and printed `[SUCCESS]` while the real file was untouched.
  - OpenClaw parser also scanned the stale default `~/.openclaw/workspace/skills` path; a leftover SKILL.md there pointed at a different project, splitting the table.
- Both fixed: OpenCode now writes to the real XDG path; OpenClawParser resolves ONLY the real workspace from `openclaw.json` (`agents.defaults.workspace`).

### Added
- `wizard clear` warns about configured agents whose path has no index (no agent vanishes silently).

## [1.1.35] - 2026-07-27

### Fixed
- OpenClaw parser reads the nested workspace skill (`agents.defaults.workspace` in `openclaw.json`), matching where wizard writes it. Previously the parser used a hardcoded default path and dropped OpenClaw from `wizard clear` after a clean wizard setup.

## [1.1.34] - 2026-07-27

### Fixed
- `wizard clear` now collects agents whose configured path has no index and prints a Warning panel (configured path + guidance), so missing agents are visible instead of silently dropped.

## [1.1.33] - 2026-07-27

### Fixed
- `find_codenexus_index()` walks DOWN one level from an ancestor path to locate the index (agent config pointing at a parent dir now resolves correctly).
- `wizard clear` merges agents from every path that resolves to the same index dir into a single entry instead of dropping duplicates.

## [1.1.32] - 2026-07-27

### Changed
- `wizard clear` renders one Panel per index. Each block shows Agents / Project Path / Size on their own lines under the `idx-N` title, so columns never interleave and Size is clearly its own row.

## [1.1.31] - 2026-07-27

### Fixed
- `wizard clear` table: fixed path truncation and row-height misalignment by keeping each cell's line count in sync per row.

## [1.1.30] - 2026-07-27

### Fixed
- `wizard clear` table renders long paths without truncation (compact `~` form, `overflow="fold"` + `no_wrap`).

## [1.1.29] - 2026-07-27

### Added
- OpenCode and Antigravity agent support (config generation + parsers).
- Productization: structured `pipeline` output, license/memory/llm gates wired through `server.py` as single source of truth, `mcp_server.py` thin transport.

## [1.1.28] - 2026-07-25

### Fixed
- Server version string made explicit (`Server("codenexus", version=...)`) so `serve` reports the real version instead of the SDK default.

## [1.1.27] - 2026-07-25

### Docs
- **Token savings example updated to a real measurement.** The old README claimed "50-70%" / "74% reduction" with a 8,247→2,140 example. Replaced with numbers measured on the `openclaw_workspace/projects` index (211 files, 4,224 nodes): sending the whole codebase = **951,322 tokens** vs. `run_pipeline` average **~4,325 tokens/task** → **~99.5% reduction**. Applied to both `README.md` and `README.ko.md`.
- **MCP compatibility clarified.** Both READMEs now state CodeNexus is built on the official `mcp` Python SDK (standard `Content-Length` framed stdio) and lists all 9 MCP agents (Hermes, Claude Code, Cursor, Windsurf, Zed, Continue.dev, GitHub Copilot, Codex, Augment) as supported. Added a note in the troubleshooting section that the server speaks the standard MCP protocol so any spec-compliant client connects out of the box.

## [1.1.26] - 2026-07-25

### Fixed
- **CI test `test_get_context_capsule_returns_results` failed** on GitHub Actions: it hard-coded the host path `/home/rudylee/openclaw_workspace/projects`, which does not exist in CI, causing `FileNotFoundError` → `Connection closed`. Rewrote the test to build a tiny project inside pytest's `tmp_path` fixture (`codenexus -w <tmp> index` — note: `-w` comes *before* the `index` subcommand) and assert a non-empty capsule. This also keeps the test host-independent and re-runnable.

## [1.1.25] - 2026-07-25

### Fixed
- **`get_context_capsule` returned an empty capsule for multi-word queries.** It passed the whole query string (e.g. `"authentication login"`) straight to `graph.search_nodes()`, which only matches single tokens, so most real queries returned nothing. `run_pipeline` already split the query into keywords and OR-merged results; applied the same keyword-split + dedup logic to `_get_context_capsule` so it returns real nodes. Verified end-to-end over stdio: `get_context_capsule("authentication login")` now returns a 3.8 KB capsule (was 0 bytes before).

### Added
- Test `test_get_context_capsule_returns_results` — boots the server over real stdio, calls `get_context_capsule` with a multi-word query, and asserts a non-empty capsule + positive token estimate.

## [1.1.24] - 2026-07-25

### Fixed
- **Hermes (and all standard MCP clients) could not connect to the CodeNexus MCP server.** `mcp_server.py` spoke newline-delimited JSON-RPC over stdio, but the `mcp` Python SDK (used by Hermes, Claude Code, Cursor, etc.) expects the framed `Content-Length` transport. Clients failed with `Connection closed` and parked the server. Rewrote `mcp_server.py` on top of the official `mcp` SDK (`Server` + `stdio_server`), so it now speaks the standard MCP stdio protocol. All 4 tools (`run_pipeline`, `get_context_capsule`, `get_skeleton`, `index_status`) are registered via the SDK decorator API.

### Added
- Test `test_mcp_server_registers_tools` — boots the server over real stdio and asserts all 4 tools are exposed (catches any future transport regression).
- `mcp` is already a declared dependency (`mcp>=1.0.0`).

## [1.1.23] - 2026-07-25

### Fixed
- **`wizard clear` did not list OpenClaw indexes.** `get_all_indexed_projects()` only parsed MCP-based agents (Claude Code, Hermes, Cursor, Codex) and silently ignored OpenClaw, which configures CodeNexus via a `SKILL.md` file rather than an MCP block. Added `OpenClawParser` that extracts the `-w <path>` from the skill definition, and registered it in `get_all_indexed_projects()` so `wizard clear` now shows OpenClaw alongside the MCP agents.

### Added
- Tests: `test_openclaw_parser_extracts_path`, `test_get_all_indexed_projects_includes_openclaw`.

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
