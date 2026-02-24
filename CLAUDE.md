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

## Roadmap

See ROADMAP.md. Currently at Step 0 (scaffolding complete). Next: Phase 1 (single-turn tests).
