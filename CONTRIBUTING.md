# Contributing to Skillspar

Thanks for your interest in contributing! This document covers how to set up a
development environment, run the checks, and submit changes.

## Development setup

We use [uv](https://docs.astral.sh/uv/) for package management:

```bash
git clone https://github.com/kynetyk-ai/skillspar.git
cd skillspar
uv sync --extra dev        # creates .venv/ and installs all dev dependencies
```

Prefer plain pip? That works too — the project is standard PEP 621 packaging:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and add your `ANTHROPIC_API_KEY` if you want to
run eval suites against the live API. The test suite is fully mocked and does
not need a real key.

## Running checks

All of these must pass before a PR can merge (CI enforces them):

```bash
uv run pytest                            # test suite
uv run ruff check src/                   # lint
uv run ruff format --check src/ tests/   # formatting
uv run pyright src/                      # type check
```

Optionally install the pre-commit hooks to run ruff automatically:

```bash
uv run pre-commit install
```

## Pull request workflow

1. Branch off `develop` (not `main`) and open your PR against `develop`.
2. Keep PRs focused — one logical change per PR.
3. Write tests alongside new code; run the full check suite before pushing.
4. Fill in the PR template.

## Code style expectations

- Python 3.11+, Pydantic v2 for config schemas, `click` for CLI, `rich` for
  console output.
- Use module-level loggers (`logging.getLogger(__name__)`), not `print` —
  DEBUG for internal flow, INFO for user-visible events, WARNING for
  recoverable issues, ERROR for failures.
- Robust error handling at boundaries (user input, file I/O, API calls, config
  parsing) — surface clear messages, not raw tracebacks.
- Validate early: Pydantic validators on schemas rather than runtime checks
  deep in the engine.

## Keeping docs in sync

The `/skillspar:evaluate` skill package (`skills/evaluate/`) and the docs are
first-class deliverables. If your change touches the `.eval.yaml` schema,
assertion types, or CLI behavior, update the matching references — see the
"After major changes" section of [CLAUDE.md](CLAUDE.md) for the checklist.

## Reporting bugs and requesting features

Use the [issue templates](https://github.com/kynetyk-ai/skillspar/issues/new/choose).
For security issues, see [SECURITY.md](SECURITY.md) — please do not open a
public issue.
