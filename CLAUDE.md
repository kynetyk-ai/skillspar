# Skillspar — Development Guide

## Virtual Environment

This project uses a Python virtual environment at `.venv/`. Always use it for running commands:

```bash
.venv/bin/pip install -e ".[dev]"   # install/update deps
.venv/bin/skill-eval ...            # run the CLI
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
- CLI built with `click`, entry point is `skill-eval`
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
  1. `skills/evaluate-skill/references/eval-schema-reference.md` — the schema reference the meta-skill reads
  2. `skills/evaluate-skill/references/assertion-types-reference.md` — if assertion types changed
  3. `skills/evaluate-skill/SKILL.md` — if the change affects test design guidance
  4. `examples/` — ensure example suites still parse and demonstrate the current schema
- **Feature additions**: When a phase milestone is reached, re-evaluate the README and any user-facing docs for accuracy.
- **Skill package coherence**: The `/evaluate-skill` skill package (SKILL.md + references/) is a first-class deliverable. Treat it like code — if the framework changes, the skill must stay in sync.

## Roadmap

See ROADMAP.md. Phases 1–4A complete. Next: Phase 4B (schema stabilization & mid-conversation testing).
