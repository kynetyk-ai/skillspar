# Code Review: Skillspar — Production Readiness Assessment

## Context

This is a quality review of the Skillspar codebase (~4,700 LOC, 39 source files, 526 tests) prior to Phase 5 (release readiness). The project is a declarative testing harness for Claude Code Agent Skills, distributed both as a CLI (`skillspar`) and a Claude Code plugin.

**Overall verdict: The codebase is well-engineered.** The architecture is clean, error handling is thorough, and the test suite is comprehensive. What follows are the issues worth addressing before a public release, ranked by severity.

---

## Critical / High Priority

### 1. Significant code duplication in `runner.py`

**Files:** `src/skill_evaluator/runner.py:255-392`

`_run_single_turn` and `_run_multi_turn` are ~70% identical. Both methods:
- Resolve context files with identical try/except/return-ERROR blocks (lines 262-276 vs 329-343)
- Build skill messages, prefix messages, test messages in the same way (lines 278-285 vs 345-352)
- Strip `skill_only` messages for baselines identically (lines 282-283 vs 349-350)
- Merge messages identically (line 284 vs 351)
- Wrap execution in identical try/except blocks returning ERROR results (lines 290-307 vs 364-379)
- Call `evaluate_assertions` identically (lines 310-314 vs 382-386)
- Also both do inline imports of `AssertionResult, AssertionStatus` inside error handlers (lines 265-266, 295-296, 332-333, 367-368) — these should be top-level imports

**Recommendation:** Extract the shared setup (context resolution, message building, error wrapping) into a private method, reducing both to thin wrappers that differ only in the executor instantiation and call.

### 2. `_run_suite_and_build_report` duplicates `_run_single_suite` logic

**File:** `src/skill_evaluator/cli.py:347-383`

The snapshot commands (`save`, `diff --latest`) go through `_run_suite_and_build_report`, which duplicates the load → resolve → execute → report → JSON pipeline from `_run_single_suite`. If either path changes, the other must be manually kept in sync.

**Recommendation:** Extract a shared `_load_and_execute` helper, or have `_run_suite_and_build_report` delegate to common primitives with `_run_single_suite`.

### 3. `ResolvedConfig` duplicates `SuiteDefaults` field definitions

**File:** `src/skill_evaluator/config/schema.py:239-249 vs 318-334`

Both models declare the same fields (`model`, `judge_model`, `max_tokens`, `temperature`, `runs`, `pass_threshold`, `max_retries`, `concurrency`, `enable_caching`) with the same defaults. Updating one without the other is a latent bug.

**Recommendation:** Have `ResolvedConfig` inherit from or compose `SuiteDefaults`, adding only the CLI-specific fields (`output`, `output_format`, `verbose`, `filter_pattern`). Or extract a shared base.

---

## Medium Priority

### 4. Missing validation on `ToolCalledTimesAssertion` and `TurnCountAssertion`

**File:** `src/skill_evaluator/config/schema.py:56-80`

Both models accept a state where `min`, `max`, and `exactly` are ALL `None`. In this case the assertion silently always passes — the user thinks they're testing something when they're not.

Similarly, specifying `min=5, max=2` (contradictory bounds) is accepted but will always fail.

**Recommendation:** Add a `@model_validator(mode="after")` requiring at least one bound, and validating `min <= max` when both are set.

### 5. Overly broad `except Exception` in execution paths

**Files:**
- `src/skill_evaluator/runner.py:294, 366` — catches _any_ exception from `executor.execute()`
- `src/skill_evaluator/engine/single_turn.py:91` — catches any exception from `self.client.messages.create()`
- `src/skill_evaluator/engine/multi_turn.py:66` — same

While `except Exception` won't catch `KeyboardInterrupt` or `SystemExit`, it WILL catch `TypeError`, `AttributeError`, `KeyError`, etc. — genuine bugs in the code that should crash loudly during development, not be silently wrapped in an ERROR assertion result.

**Recommendation:** Catch `anthropic.APIError` (or `anthropic.APIConnectionError`, `anthropic.RateLimitError`, etc.) specifically. Let programming errors propagate.

### 6. No pre-flight `ANTHROPIC_API_KEY` check

**File:** `src/skill_evaluator/cli.py:106-111`

The CLI calls `load_dotenv()` but never verifies the key exists before entering the execution pipeline. When the key is missing, the error emerges from deep inside the Anthropic SDK as a cryptic `AuthenticationError`, long after the suite has been loaded and validated.

**Recommendation:** Add a quick `os.environ.get("ANTHROPIC_API_KEY")` check after `load_dotenv()` with a user-friendly error message.

### 7. JSONPath parsing not guarded with a specific error message

**File:** `src/skill_evaluator/assertions/structural.py:82`

`jsonpath_parse(assertion.path)` will raise a generic `JsonPathParserError` if the user provides an invalid JSONPath expression. While the evaluator's outer `except Exception` in `evaluator.py:109` catches this and returns an ERROR result, the message is `"Error evaluating assertion: ..."` rather than something like `"Invalid JSONPath expression: ..."`.

**Recommendation:** Wrap `jsonpath_parse` in a try/except to produce a clear diagnostic:
```python
try:
    expr = jsonpath_parse(assertion.path)
except Exception as e:
    return AssertionResult(
        status=AssertionStatus.ERROR,
        assertion_type="tool_args_match",
        message=f"Invalid JSONPath expression '{assertion.path}': {e}",
    )
```

---

## Low Priority / Nits

### 8. Hardcoded `MINIMUM_CACHE_TOKEN_THRESHOLD`

**File:** `src/skill_evaluator/engine/prefix.py:15`

`MINIMUM_CACHE_TOKEN_THRESHOLD = 1024` is a module-level constant with no way to override it. For a framework that exposes most knobs via config, this one is surprisingly rigid.

**Recommendation:** Consider making it configurable via `SuiteDefaults`, or at least document it as a known fixed threshold.

### 9. `multi_turn.py:102` has confusing content serialization logic

```python
"content": json.dumps(matched) if not isinstance(matched.get("content"), str) else matched["content"],
```

This ternary does two things: checks if the matched response has a `"content"` key that's already a string, and if not, serializes the entire dict. The intent is unclear and the edge cases are non-obvious.

**Recommendation:** Extract to a named helper like `_serialize_tool_result(matched)` with a brief docstring.

### 10. Missing `py.typed` marker

**File:** not present in `src/skill_evaluator/`

Without a `py.typed` file, type checkers won't resolve types from this package when it's installed as a dependency.

**Recommendation:** Add an empty `src/skill_evaluator/py.typed` file.

### 11. Output truncation in assertion details is undocumented

**File:** `src/skill_evaluator/assertions/deterministic.py:46, 64, 82`

Failed assertions include `{"output": text[:500]}` — silently truncating to 500 characters. For long model responses, the truncated output may cut off exactly the part the user needs to debug.

**Recommendation:** Either include the truncation in the message (`"(output truncated to 500 chars)"`), or make the limit configurable, or at least document the behavior.

---

## Strengths Worth Highlighting

These patterns demonstrate engineering maturity and should be preserved:

- **Discriminated unions** (`Field(discriminator="type")`) for extensible assertion and test types — exactly right for a schema that needs to support future types without breaking existing ones
- **Frozen models and dataclasses** (`ResolvedConfig(frozen=True)`, `@dataclass(frozen=True)` on Trace models) — prevents accidental mutation of shared state
- **Exception hierarchy** — every module defines its own specific exception type with proper `from e` chaining
- **Config precedence** documented and implemented correctly: hardcoded → env → YAML → CLI
- **`__test__ = False`** on `TestResult`/`TestRunGroup` — prevents pytest from collecting these as test classes
- **`yaml.safe_load()`** everywhere — no YAML deserialization vulnerabilities
- **Zero subprocess calls** — no command injection surface
- **NullHandler pattern** in `__init__.py` — correct library logging convention
- **Message coalescing** (`_coalesce_consecutive_roles`) — handles the Anthropic API's requirement for alternating roles cleanly
- **Work item batching** in `runner.py` — skill runs first, then baseline runs, maximizing cache hits
- **Test fixtures** (`conftest.py`) — well-designed factory fixtures for mock API responses

---

## Pre-Release Checklist (Phase 5 Blockers)

Not code quality issues, but items the roadmap already identifies:

| Item | Status |
|------|--------|
| `pyproject.toml` missing `[project.urls]`, `[project.authors]`, `[project.classifiers]` | Needed for PyPI |
| No GitHub Actions CI/CD | Blocks public release |
| No `CHANGELOG.md` | Needed for release notes |
| No `py.typed` marker | Blocks typed library consumers |
| No mypy/pyright enforcement | Type annotations exist but unenforced |
| Ruff config uses only default rules | Should enable `I` (isort), `B` (bugbear), `UP` (pyupgrade) |
| 5 line-length violations (E501) | `cli.py:75,100,302`, `llm_judge.py:125`, `conversation.py:40` |

---

## Verification

After addressing the above items:

1. `cd /Users/joshuaziel/Documents/coding/skill-evaluator`
2. `.venv/bin/ruff check src/` — should be clean
3. `.venv/bin/pytest` — all 526 tests should pass
4. `.venv/bin/skillspar run examples/basic.eval.yaml` — smoke test (requires API key)
5. Manually verify that the renamed/refactored methods in `runner.py` don't change behavior by running a multi-turn example: `.venv/bin/skillspar run examples/multi-turn.eval.yaml`
