# CodeNexus

AI coding agents working in this repository follow the rules below. They exist
because v1.1.x shipped defects that all tests passed with — tests that
verified the implementation's own assumptions instead of observable behavior.

## Verification rules (non-negotiable)

1. **No change is "done" without**: `pytest` fully green AND `ruff check codenexus/ tests/` clean.
2. **Fixes follow the red→green protocol**: write a test reproducing the defect FIRST, show it FAILING against the unfixed code (paste the output), then fix, then show it PASSING. A test that never went red proves nothing about the bug.
3. **New features follow the same protocol**: capture acceptance criteria as failing tests before implementing (red→green again).
4. **Tests must measure observable behavior** — DB roundtrips, CLI output, MCP protocol responses — not internal call order or tautologies re-stating the implementation.
5. **"It works" claims require reproducible evidence** (the command and its output). If a claim can't be demonstrated, say so explicitly. When challenged, produce the red-state output; inability to means the loop was skipped.
6. **Report what is NOT covered.** Every task summary lists which modules/paths remain untested.

## Release safety

- Tags trigger PyPI auto-deploy via GitHub Actions. **Never push a release tag without explicit user approval in the current conversation.**
- Commits accumulate locally during a work session; push when the user asks (batch pushes at completion).

## Project layout notes

- Single source of version truth: `codenexus/_version.py` (pyproject must match).
- Both MCP implementations (`server.py` SDK-based, `mcp_server.py` stdio loop) must share behavior through `codenexus/pipeline.py` — do not fork logic between them again.
- Index schema changes bump `SCHEMA_VERSION` in `graph.py` so existing `.db` files migrate once on open.
