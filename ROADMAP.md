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

## Phase 4B: Feedback Loop

CLI result interpretation and iterative improvement of generated suites.

- [ ] CLI result interpretation guidance (reading pass/fail output, understanding baseline deltas)
- [ ] Suggest improvements to generated suites based on test results (flaky tests, weak assertions, missing coverage)
- [ ] Iterative refinement workflow documentation

**Milestone**: After running a generated suite, the user gets actionable guidance on improving both the suite and the skill.

## Phase 4C: Documentation + README

- [ ] Documentation refresh
- [ ] Re-evaluate README prior to final release

## Phase 4D: Watch Mode (Fast Iteration Feedback)

Tight edit→test loop for skill authors. Re-run suites automatically on file changes.

- [ ] Extract `run` logic from `cli.py` into a reusable `execute_suite()` function that returns a result code (prerequisite for watch loop and exit code refinement)
- [ ] Fix dual source of truth: runner reads `ResolvedConfig` exclusively, remove `suite.defaults` back-sync in `cli.py`
- [ ] Add `watchfiles` dependency (Rust-backed, reliable on macOS)
- [ ] `skillspar watch` subcommand: initial full run, then re-run affected suites on SKILL.md / YAML / context file changes
- [ ] Debounced change detection (300ms window)
- [ ] Rich live display: clear and re-render pass/fail summary on each iteration

**Milestone**: `skillspar watch suite.yaml` re-runs on save and shows live pass/fail output.

## Phase 4E: Stored Baselines & Temporal Diffing

Snapshot results over time and detect steer erosion — when a skill's behavioral delta shrinks across runs.

- [ ] Enrich JSON report: add `schema_version`, `run_id`, skill file hash; include `judge_model` and `system_prompt` in defaults; fix `TokenUsage.to_dict()` to stop dropping cache tokens
- [ ] Snapshot reader/deserializer (`src/skill_evaluator/reporting/snapshot.py`)
- [ ] Diff engine (`src/skill_evaluator/reporting/diff.py`): per-test pass_rate_delta, assertion flips, steer erosion detection (baseline pass rate rising → skill becoming redundant)
- [ ] Snapshot CLI: `skillspar snapshot save`, `skillspar snapshot diff`
- [ ] `.skillspar/snapshots/` storage directory (git-friendly, per-project, optional `--snapshot-dir` override)
- [ ] Console delta display: show what flipped when comparing against a previous snapshot
- [ ] Enhance watch mode: display assertion flips against previous iteration (building on diff engine)

**Milestone**: `skillspar snapshot diff` shows per-test pass-rate deltas and flags steer erosion between runs.

## Phase 4F: CI & Team Workflow

Multi-suite execution, cost tracking, and CI-friendly exit codes for team-scale usage.

- [ ] Exit code refinement: 0 = all passed, 1 = tests failed, 2 = config/validation error
- [ ] Cost tracking: pricing table, `estimate_cost()`, cost section in JSON report summary, `SKILLSPAR_PRICING_FILE` env var override
- [ ] Duration tracking: `duration_seconds` on `TestResult`, `time=` attributes in JUnit XML
- [ ] Multi-suite runner: `skillspar run` accepts multiple files, globs, or directories
- [ ] Multi-suite summary reporter: aggregated dashboard view across a skill library (table of suite name, pass/fail, cost, baseline delta)

**Milestone**: `skillspar run examples/ --format junit` runs all suites, exits with distinct codes, and includes cost + duration in reports.

## Phase 4G: Mid-Conversation Skill Testing & Prompt Caching

Test whether a skill still steers model behavior when preceded by a long, unrelated
conversation — the realistic scenario where a user has been chatting for a while before
triggering the skill. Uses Anthropic prompt caching so the prefix doesn't multiply
token costs across all tests in the suite.

Depends on **4E** (cache token export in `TokenUsage.to_dict()`) and **4F** (cost tracking
with `estimate_cost()`) so that cache savings are visible in reports and priced correctly
(1.25× writes, 0.1× reads).

- [ ] `ConversationPrefixConfig` schema: inline `messages` list or external YAML `file`
      reference, with validation for role alternation and assistant-final requirement
- [ ] Prefix loader (`engine/prefix.py`): resolve external files, validate structure
- [ ] Message ordering: skill_messages + prefix_messages + context_messages + test.input.messages;
      prefix present in both skill and baseline runs
- [ ] Structured system prompt: convert `system` parameter from plain string to content blocks
      with `cache_control` when caching is enabled
- [ ] `cache_control` injection on messages: mark last prefix message as cache breakpoint;
      add `cache_control` field to `MessageConfig` so markers survive role coalescing
- [ ] `enable_caching` field on `SuiteDefaults` / `ResolvedConfig` (default: `true`)
- [ ] Minimum-token-threshold warning when prefix is too short for effective caching (~1024 tokens)
- [ ] Cache reporting: `cache_summary` in JSON report (writes, reads, estimated savings);
      console one-liner when caching is active
- [ ] Example suite: `examples/mid-conversation.eval.yaml` with a multi-turn prefix

**Milestone**: `skillspar run mid-conversation.eval.yaml` prepends a simulated conversation,
caches the shared prefix across all tests, and reports cache hit rates in the output.

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
- [x] Steer strength metric — quantify the delta between skill and baseline pass rates — *subsumed by Phase 4E (steer erosion detection, pass_rate_delta)*
- [x] Snapshot testing (golden trace diffing for tool call sequences) — *subsumed by Phase 4E (stored baselines & temporal diffing)*
- [x] Flakiness detection (run N times, report variance) — *done in Phase 1 (repeated runs + pass_threshold)*
- [ ] A/B model comparison (same skill across model versions — does the steer hold?)
- [ ] Response caching for faster re-runs
- [x] Centralized config (consolidate env vars, CLI flags, YAML defaults, and .env into a unified config layer)
- [x] Structured logging (replace ad-hoc output with configurable log levels for debugging, execution traces, and CI diagnostics)
