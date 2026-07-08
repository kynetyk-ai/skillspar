# Skillspar — Development Guide

## Virtual Environment

This project uses a Python virtual environment at `.venv/`. Always use it for running commands:

```bash
.venv/bin/pip install -e ".[dev]"   # install/update deps
.venv/bin/skillspar ...             # run the CLI (or skill-eval)
.venv/bin/pytest                    # run tests
.venv/bin/ruff check src/           # lint
```

## Project Structure

- `src/skill_evaluator/` — main package (src layout)
- `tests/` — pytest test suite
- `examples/` — example `.eval.yaml` suites and sample skills
- `pyproject.toml` — project config, deps, and tool settings

## Key Conventions

- Python 3.11+, Pydantic v2 for all config schemas
- `hatch` build backend with src layout
- CLI built with `click`, entry points are `skillspar` (primary) and `skill-eval` (alias)
- Console output uses `rich`
- Async where needed (`pytest-asyncio` for async tests)

## Development Approach

### Code quality basics
- Robust error handling at every boundary: user input, file I/O, API calls, config parsing. Surface clear error messages, not raw tracebacks.
- Use the project's structured logging (`skill_evaluator.logging`) — not print statements. Log at appropriate levels: DEBUG for internal flow, INFO for user-visible events, WARNING for recoverable issues, ERROR for failures.
- Write tests alongside new code. Run `pytest` before considering a task complete.
- Validate early: Pydantic validators on config schemas, not runtime checks deep in the engine.

### After major changes
- **Schema changes**: When the `.eval.yaml` input schema changes (new fields, renamed fields, structural shifts), update:
  1. `skills/evaluate/references/eval-schema-reference.md` — the schema reference the meta-skill reads
  2. `skills/evaluate/references/assertion-types-reference.md` — if assertion types changed
  3. `skills/evaluate/SKILL.md` — if the change affects test design guidance
  4. `examples/` — ensure example suites still parse and demonstrate the current schema
- **Feature additions**: When a phase milestone is reached, re-evaluate the README and any user-facing docs for accuracy.
- **Skill package coherence**: The `/skillspar:evaluate` skill package (SKILL.md + references/) is a first-class deliverable. Treat it like code — if the framework changes, the skill must stay in sync.

## Claude Code Plugin

This repo also serves as a Claude Code plugin root:

- `.claude-plugin/plugin.json` — plugin manifest
- `skills/evaluate/` — the `/skillspar:evaluate` skill (auto-discovered by the plugin system)
- `hooks/hooks.json` — `SessionStart` hook that checks for CLI installation

Test the plugin locally: `claude --plugin-dir .`

When the version in `pyproject.toml` changes, update `.claude-plugin/plugin.json` to match.

## Roadmap

See ROADMAP.md. Phases 1–5A complete. Next: Phase 5B (release readiness), then 5C (OpenAI-compatible providers) and 5D (public launch).
