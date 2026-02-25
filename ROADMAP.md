# Roadmap

## Core Thesis

A skill is a system prompt. Skillspar measures the **steer** — the marginal behavioral impact of that prompt. Baseline comparison (`baseline: true`) answers the question generic eval frameworks don't ask: *"Is this skill worth having, or is it context bloat?"* If the model behaves the same with and without the skill, the skill is dead weight. If behavior diverges, the skill is doing real work.

## Phase 1: Foundation — Single-Turn Tests ✅

Core infrastructure for running single-turn eval suites.

- [x] Pydantic config schema (minimal subset: suite metadata, single-turn tests, basic assertions)
- [x] SKILL.md parser (YAML frontmatter extraction + body content)
- [x] Conversation builder (YAML messages to Anthropic API message format)
- [x] Trace data model (captures API response, tool calls, token usage)
- [x] SingleTurnExecutor (one `messages.create()` call, returns Trace)
- [x] Basic assertions: `tool_called`, `tool_not_called`, `output_contains`, `output_not_contains`, `output_matches_regex`, `stop_reason`
- [x] Console reporter (Rich-based pass/fail output)
- [x] CLI entry point: `skill-eval run <file.yaml>`
- [x] Working example suite with a synthetic test skill
- [x] Context file injection (suite-level and per-test `context` with line ranges)
- [x] Repeated runs (`runs: N` per suite/test, `pass_threshold` for pass rate gating)
- [x] Baseline comparison (`baseline: true` runs with and without skill prompt)
- [x] Concurrent execution (`concurrency: N` via ThreadPoolExecutor)
- [x] Structured JSON report output (`--output results.json`, non-lossy traces)
- [x] CLI overrides: `--runs`, `--concurrency`, `--output`
- [x] `.env.example` + `.gitignore` for secrets management

**Milestone**: `skill-eval run examples/basic.eval.yaml` produces pass/fail output. ✅

## Phase 2: Multi-Turn + Mock Responses ✅

Agentic loop execution with scripted tool responses.

- [x] Built-in tool schemas (Read, Write, Edit, Bash, Glob, Grep)
- [x] Tool response matcher (match by tool name, wildcards, null catch-all)
- [x] Response sequences (different responses for repeated calls to same tool)
- [x] MultiTurnExecutor (loop: API call → match tool calls → inject responses → repeat)
- [x] Extended assertions: `tool_sequence`, `tool_called_times`, `tool_args_match`, `turn_count`
- [x] Suite defaults with per-test overrides (model, max_tokens, temperature) — *done in Phase 1*

**Milestone**: Multi-turn eval suites with scripted tool responses execute correctly. ✅

## Phase 3: LLM Judge + CI Integration ✅

Quality assertions and CI-friendly output formats.

- [x] `llm_judge` assertion type (separate API call with criteria + verdict parsing)
- [x] JSON structured report output — *done in Phase 1*
- [x] JUnit XML report output
- [x] Token counting and cost estimation in reports — *done in Phase 1 (JSON report includes total_tokens)*
- [x] CLI flags: `--output` — *done in Phase 1, fixed path handling in Phase 3*
- [x] CLI flags: `--format`, `--filter`, `--model`, `--verbose`
- [x] Parallel test execution (ThreadPoolExecutor) — *done in Phase 1*
- [x] Verbose console output (per-assertion details, per-run breakdown)

**Milestone**: `skillspar run suite.yaml --format junit --output results.xml` works in CI. ✅

## Phase 4A: `/evaluate-skill` Meta-Skill ✅

A SKILL.md that guides Claude Code through analyzing a target skill and generating a test suite. This is the key differentiator — no other tool can read a skill definition and automatically propose what to test, with baseline enabled by default so every generated suite answers "is this skill worth the context?"

- [x] `/evaluate-skill` SKILL.md with analysis protocol, inline schema reference, assertion selection rules, and baseline strategy
- [x] Skill structure analysis: extract behavioral claims by category (output format, content rules, tone/style, tool-use patterns, workflow sequences, constraints/boundaries)
- [x] Assertion type guidance: `llm_judge` for subjective quality, deterministic assertions for structural behaviors. Explicit warning against using `output_contains`/`output_matches_regex` as proxies for subjective quality.
- [x] Single-turn vs multi-turn decision rules (prefer single-turn, use multi-turn only for tool-use workflows)
- [x] Test generation conventions (verb-first names, one test per claim, holistic llm_judge test, realistic user messages)
- [x] Example code review skill (`examples/code-review-skill/SKILL.md`) with both structural and subjective requirements
- [x] Hand-validated reference eval suite (`examples/code-review-skill.eval.yaml`) — 9 tests demonstrating all assertion types with baseline

**Milestone**: `/evaluate-skill my-skill/SKILL.md` generates a starter test suite that proves whether the skill changes model behavior. ✅

## Phase 4B: Schema Stabilization & Mid-Conversation Testing ✅

Finalize the YAML input schema before building features on top. The headline addition is
mid-conversation skill testing — prepending a simulated conversation to measure whether a
skill still steers behavior after context dilution. Also includes internal refactoring that
unblocks later phases.

### YAML schema additions
- [x] `conversation_prefix` on `EvalSuite`: `ConversationPrefixConfig` schema with inline
      `messages` list or external YAML `file` reference; validation for role alternation and
      assistant-final requirement
- [x] Prefix loader (`engine/prefix.py`): resolve external files, validate structure
- [x] Message ordering: skill_messages + prefix_messages + context_messages + test.input.messages;
      prefix present in both skill and baseline runs
- [x] `cache_control` field on `MessageConfig`: mark last prefix message as cache breakpoint;
      tag survives `_coalesce_consecutive_roles()` by propagating during merge
- [x] `enable_caching` field on `SuiteDefaults` / `ResolvedConfig` (default: `true`)
- [x] Structured system prompt: convert `system` parameter from plain string to content blocks
      with `cache_control` when caching is enabled (two cache breakpoints: system prompt shared
      across all requests, last prefix message shared within each skill/baseline group)

### Internal refactoring
- [x] Extract `run` logic from `cli.py` into a reusable `execute_suite()` function that
      returns a result code (prerequisite for watch mode and multi-suite runner)
- [x] Fix dual source of truth: runner reads `ResolvedConfig` exclusively, remove
      `suite.defaults` back-sync in `cli.py`
- [x] Fix `TokenUsage.to_dict()` to stop dropping cache tokens

### Example & validation
- [x] Minimum-token-threshold warning when prefix is too short for effective caching (~1024 tokens)
- [x] Example suite: `examples/mid-conversation.eval.yaml` with a multi-turn prefix

**Milestone**: `skillspar run mid-conversation.eval.yaml` prepends a simulated conversation,
caches the shared prefix across all tests, and the YAML input schema is stable. ✅

## Phase 4C: Reporting & Cost ✅

Enrich report output with cost, duration, cache visibility, and structural metadata.
No YAML input changes — this is all about what comes *out* of a run.

- [x] Enrich JSON report: add `schema_version`, `run_id`, skill file hash; include
      `judge_model` and `system_prompt` in defaults
- [x] Cost tracking: pricing table, `estimate_cost()`, cache pricing (1.25× writes, 0.1× reads),
      cost section in JSON report summary, `SKILLSPAR_PRICING_FILE` env var override
- [x] Duration tracking: `duration_seconds` on `TestResult`, `time=` attributes in JUnit XML
- [x] Cache reporting: `cache_summary` in JSON report (writes, reads, estimated savings);
      console one-liner when caching is active
- [x] Exit code refinement: 0 = all passed, 1 = tests failed, 2 = config/validation error

**Milestone**: JSON and JUnit reports include cost, duration, and cache hit rates; exit codes
are CI-friendly. ✅

## Phase 4D: Stored Baselines & Temporal Diffing

Snapshot results over time and detect steer erosion — when a skill's behavioral delta
shrinks across runs.

- [ ] Snapshot reader/deserializer (`src/skill_evaluator/reporting/snapshot.py`)
- [ ] Diff engine (`src/skill_evaluator/reporting/diff.py`): per-test pass_rate_delta,
      assertion flips, steer erosion detection (baseline pass rate rising → skill becoming redundant)
- [ ] Snapshot CLI: `skillspar snapshot save`, `skillspar snapshot diff`
- [ ] `.skillspar/snapshots/` storage directory (git-friendly, per-project, optional
      `--snapshot-dir` override)
- [ ] Console delta display: show what flipped when comparing against a previous snapshot

**Milestone**: `skillspar snapshot diff` shows per-test pass-rate deltas and flags steer
erosion between runs.

## Phase 4E: Watch Mode

Tight edit→test loop for skill authors. Re-run suites automatically on file changes.
Builds on `execute_suite()` (4B) and optionally on the diff engine (4D) for showing
assertion flips between iterations.

- [ ] Add `watchfiles` dependency (Rust-backed, reliable on macOS)
- [ ] `skillspar watch` subcommand: initial full run, then re-run affected suites on
      SKILL.md / YAML / context file changes
- [ ] Debounced change detection (300ms window)
- [ ] Rich live display: clear and re-render pass/fail summary on each iteration
- [ ] Display assertion flips against previous iteration (building on 4D diff engine)

**Milestone**: `skillspar watch suite.yaml` re-runs on save and shows live pass/fail output.

## Phase 4F: CI, Multi-Suite & Documentation

Multi-suite execution for team-scale usage, plus documentation that reflects the now-stable
schema and feature set.

- [ ] Multi-suite runner: `skillspar run` accepts multiple files, globs, or directories
- [ ] Multi-suite summary reporter: aggregated dashboard view across a skill library
      (table of suite name, pass/fail, cost, baseline delta)
- [ ] CLI result interpretation guidance (reading pass/fail output, understanding baseline deltas)
- [ ] Iterative refinement workflow (improving suites based on test results: flaky tests,
      weak assertions, missing coverage)
- [ ] Documentation refresh and README re-evaluation

**Milestone**: `skillspar run examples/` runs all suites with an aggregated summary, and
documentation covers the full feature set.

## Phase 5: Release Readiness + PyPI (Future)

CI/CD, packaging metadata, error handling polish, and code quality enforcement — the gate before public release.

### CI/CD
- [ ] GitHub Actions workflow: `ruff check src/` + `pytest` on every push and PR
- [ ] `.pre-commit-config.yaml` with ruff + ruff-format hooks

### Packaging metadata (`pyproject.toml`)
- [ ] Add `[project.urls]` (Homepage, Repository, Bug Tracker)
- [ ] Add `[project.authors]`
- [ ] Add `[project.classifiers]` (Development Status, License, Python versions, Topic)

### Community files
- [ ] `CHANGELOG.md`
- [ ] `CONTRIBUTING.md`

### Error handling UX
- [ ] Catch `SkillParseError` in CLI/runner (currently surfaces as raw traceback)
- [ ] Pre-flight `ANTHROPIC_API_KEY` check with user-friendly error message

### Code quality tooling
- [ ] Configure and enforce mypy or pyright (type annotations exist but are unenforced)
- [ ] Expand ruff rule sets: add `I` (isort), `B` (bugbear), `UP` (pyupgrade)

### Cleanup
- [ ] Remove or populate empty `docs/` directory

### Distribution
- [ ] PyPI packaging and distribution (`hatch build` + `twine upload` or trusted publisher)

**Milestone**: `pip install skillspar` works from PyPI, CI is green, contributors have a documented path.

## Phase 6: Analytics + Advanced (Future)

- [ ] Sample size estimator — recommend run counts for statistically significant steer measurement
- [ ] Analytics package — standardized reporting for skill vs. baseline comparison, cross-model steer analysis, and confidence intervals
- [x] Steer strength metric — quantify the delta between skill and baseline pass rates — *subsumed by Phase 4D (steer erosion detection, pass_rate_delta)*
- [x] Snapshot testing (golden trace diffing for tool call sequences) — *subsumed by Phase 4D (stored baselines & temporal diffing)*
- [x] Flakiness detection (run N times, report variance) — *done in Phase 1 (repeated runs + pass_threshold)*
- [ ] A/B model comparison (same skill across model versions — does the steer hold?)
- [ ] Response caching for faster re-runs
- [x] Centralized config (consolidate env vars, CLI flags, YAML defaults, and .env into a unified config layer)
- [x] Structured logging (replace ad-hoc output with configurable log levels for debugging, execution traces, and CI diagnostics)
