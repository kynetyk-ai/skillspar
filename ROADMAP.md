# Roadmap

## Core Thesis

A skill is essentially a prompt. Skillspar measures the **steer** — the marginal behavioral impact of that prompt. Baseline comparison (`baseline: true`) answers the question generic eval frameworks don't ask: *"Is this skill worth having, or is it context bloat?"* If the model behaves the same with and without the skill, the skill is dead weight. If behavior diverges, the skill is doing real work.

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

## Phase 4A: `/evaluate` Meta-Skill ✅

A SKILL.md that guides Claude Code through analyzing a target skill and generating a test suite. This is the key differentiator — no other tool can read a skill definition and automatically propose what to test, with baseline enabled by default so every generated suite answers "is this skill worth the context?"

- [x] `/evaluate` SKILL.md with analysis protocol, inline schema reference, assertion selection rules, and baseline strategy
- [x] Skill structure analysis: extract behavioral claims by category (output format, content rules, tone/style, tool-use patterns, workflow sequences, constraints/boundaries)
- [x] Assertion type guidance: `llm_judge` for subjective quality, deterministic assertions for structural behaviors. Explicit warning against using `output_contains`/`output_matches_regex` as proxies for subjective quality.
- [x] Single-turn vs multi-turn decision rules (prefer single-turn, use multi-turn only for tool-use workflows)
- [x] Test generation conventions (verb-first names, one test per claim, holistic llm_judge test, realistic user messages)
- [x] Example code review skill (`examples/code-review-skill/SKILL.md`) with both structural and subjective requirements
- [x] Hand-validated reference eval suite (`examples/code-review-skill.eval.yaml`) — 9 tests demonstrating all assertion types with baseline

**Milestone**: `/evaluate my-skill/SKILL.md` generates a starter test suite that proves whether the skill changes model behavior. ✅

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

## Phase 4D: Stored Baselines & Temporal Diffing ✅

Snapshot results over time and detect steer erosion — when a skill's behavioral delta
shrinks across runs.

- [x] Snapshot I/O (`src/skill_evaluator/reporting/snapshot.py`): save, load, list, find_latest
- [x] Diff engine (`src/skill_evaluator/reporting/diff.py`): per-test pass_rate_delta,
      assertion flips, steer erosion detection (baseline pass rate rising → skill becoming redundant)
- [x] Console delta display (`src/skill_evaluator/reporting/diff_display.py`): Rich-formatted
      diff output with color-coded regressions, improvements, and steer erosion
- [x] Snapshot CLI: `skillspar snapshot save`, `skillspar snapshot diff`, `skillspar snapshot list`
- [x] `.skillspar/snapshots/` storage directory (git-friendly, per-project, optional
      `--snapshot-dir` override, `SKILLSPAR_SNAPSHOT_DIR` env var)
- [x] `--latest` mode: run suite, diff against most recent saved snapshot, save new snapshot

**Milestone**: `skillspar snapshot diff` shows per-test pass-rate deltas and flags steer
erosion between runs. ✅

## Phase 4E: Watch Mode ✅

Tight edit→test loop for skill authors. Re-run suites automatically on file changes.
Builds on `execute_suite()` (4B) and optionally on the diff engine (4D) for showing
assertion flips between iterations.

- [x] Add `watchfiles` dependency (Rust-backed, reliable on macOS)
- [x] `skillspar watch` subcommand: initial full run, then re-run affected suites on
      SKILL.md / YAML / context file changes
- [x] Debounced change detection (300ms default, configurable via `--debounce`)
- [x] Rich live display: clear and re-render pass/fail summary on each iteration
- [x] Display assertion flips against previous iteration (building on 4D diff engine)
- [x] Error resilience: syntax errors display inline, watcher continues
- [x] Dynamic watch set: re-discovers files after each successful run

**Milestone**: `skillspar watch suite.yaml` re-runs on save and shows live pass/fail output. ✅

## Phase 4F: CI, Multi-Suite & Documentation ✅

Multi-suite execution for team-scale usage, plus documentation that reflects the now-stable
schema and feature set.

- [x] Multi-suite runner: `skillspar run` accepts multiple files, globs, or directories
- [x] Multi-suite summary reporter: aggregated dashboard view across a skill library
      (table of suite name, pass/fail, cost, baseline delta)
- [x] CLI result interpretation guidance (reading pass/fail output, understanding baseline deltas)
- [x] Iterative refinement workflow (improving suites based on test results: flaky tests,
      weak assertions, missing coverage)
- [x] Documentation refresh and README re-evaluation

**Milestone**: `skillspar run examples/` runs all suites with an aggregated summary, and
documentation covers the full feature set. ✅

## Phase 4G: Claude Code Plugin Packaging ✅

Package the repo as a Claude Code plugin so users can install skillspar's `/evaluate`
skill directly into their Claude Code environment. The plugin overlays onto the existing repo
structure — no restructuring needed.

- [x] `.claude-plugin/plugin.json` manifest (name, version synced with pyproject.toml, metadata)
- [x] `hooks/hooks.json` with `SessionStart` hook: warn if `skillspar` CLI is not installed,
      with `pip install git+https://github.com/kynetyk-ai/skillspar.git` instructions
- [x] Portable paths in `/evaluate` SKILL.md (validate script path relative to skill dir)
- [x] README plugin installation section (development mode via `--plugin-dir`, CLI install via GitHub)
- [x] `marketplace.json` for self-hosted plugin marketplace
- [x] CLAUDE.md plugin structure documentation

**Milestone**: `claude --plugin-dir .` loads the plugin, `/skillspar:evaluate` is
discoverable and functional. ✅

## Phase 5A: Internal Launch ✅

Full polish for team and collaborator use — CI/CD, error handling, code quality enforcement,
and contribution workflow. Install via GitHub repo (`pip install git+...`).

### CI/CD
- [x] GitHub Actions workflow: `ruff check src/` + `ruff format --check` + `pyright` + `pytest` on every push and PR
- [x] `.pre-commit-config.yaml` with ruff + ruff-format hooks

### Packaging metadata (`pyproject.toml`)
- [x] Add `[project.urls]` (Homepage, Repository, Bug Tracker)
- [x] Add `[project.authors]`

### Error handling UX
- [x] Catch `SkillParseError` in CLI/runner — *already done in prior phases*
- [x] Pre-flight `ANTHROPIC_API_KEY` check with user-friendly error message — *already done in prior phases*
- [x] Catch `ToolRegistryError` in single-suite CLI path (gap found during 5A exploration)

### Code quality tooling
- [x] Configure and enforce pyright (`basic` mode, Python 3.11, src-only)
- [x] Expand ruff rule sets: add `I` (isort), `B` (bugbear), `UP` (pyupgrade)

### Contribution workflow
- [x] GitHub issue templates (`.github/ISSUE_TEMPLATE/`): bug report and feature request
- [x] PR template (`.github/pull_request_template.md`)

### Cleanup
- [x] `docs/` directory populated (cli-reference.md, code-review.md) — *already done in prior phases*

**Milestone**: CI is green, error messages are user-friendly, and the team has a clean
contribution workflow via GitHub. ✅

## Phase 5B: Release Readiness

Fix the gaps found in the pre-launch audit (July 2026): CI has never run and would fail,
and the community files planned for launch don't exist yet.

### CI fixes
- [ ] Make tests environment-independent: autouse fixture in `tests/conftest.py` that sets a
      dummy `ANTHROPIC_API_KEY` (16 CLI tests currently fail without a real key in the env,
      and `.github/workflows/ci.yml` sets none)
- [ ] Add `develop` to CI push triggers (workflow currently only fires on `main` pushes and
      PRs, so it has never executed)
- [ ] Verify a green Actions run on GitHub

### Community files (pulled forward from the old Phase 5C)
- [ ] `CHANGELOG.md` (0.1.0 entry)
- [ ] `CONTRIBUTING.md` (dev setup, testing, PR workflow, code style expectations)
- [ ] `CODE_OF_CONDUCT.md` (Contributor Covenant)
- [ ] `SECURITY.md` (vulnerability reporting policy)
- [ ] README contributing section (link to `CONTRIBUTING.md`, community guidelines summary)

### Metadata & doc consistency
- [ ] Add `[project.classifiers]` to `pyproject.toml` (Development Status, License, Python
      versions, Topic)
- [ ] Fix stale CLAUDE.md roadmap line (says "Next: Phase 5A"; 5A is complete)
- [ ] Set GitHub repo description and topics

**Milestone**: CI is green on GitHub, community files exist, and metadata is
launch-ready.

## Phase 5C: OpenAI-Compatible Provider Support

Add a thin provider adapter so suites can run against any OpenAI-compatible endpoint
(OpenAI, OpenRouter, LiteLLM, Ollama, vLLM) alongside Anthropic. The internal
`Trace`/`Turn`/`ToolCall` model is already provider-neutral and all assertions consume it,
so the work is confined to the API boundary: three `messages.create()` call sites, the
message builder, and the response parser. This also sets up Phase 6's A/B model comparison
as a *cross-vendor* story — "does the steer hold on other models?"

### Provider abstraction
- [ ] `providers/base.py`: protocol with
      `create_message(model, system, messages, tools, max_tokens, temperature)` returning a
      normalized response (text, tool calls, normalized stop reason
      `end_turn | tool_use | max_tokens`, usage)
- [ ] `providers/anthropic.py`: current behavior, passes `cache_control` through
- [ ] `providers/openai_compat.py`: translate canonical (Anthropic-format) messages both
      directions — system param → system message, `tool_use`/`tool_result` blocks →
      `tool_calls` + `role: "tool"` messages, `input_schema` → `function.parameters`;
      map `finish_reason` and usage fields; strip `cache_control` markers; parse tool-call
      argument JSON strings
- [ ] `openai` SDK as optional extra (`pip install skillspar[openai]`) with configurable
      `base_url` — one adapter covers all OpenAI-compatible endpoints

### Config & CLI
- [ ] `provider`, `base_url`, `api_key_env` fields on `SuiteDefaults`/`ResolvedConfig`
- [ ] `judge_provider` so the judge can stay on Claude while the model-under-test runs
      elsewhere (cross-provider comparison needs a fixed judge)
- [ ] Provider-aware API key pre-flight check in the CLI
- [ ] Normalize `stop_reason` assertion values (accept canonical values, keep Anthropic
      strings as aliases for backward compatibility)

### Reporting & degradation
- [ ] Extend pricing table schema with per-provider cache semantics (OpenAI: 0.5× cached
      reads, free writes); unknown models degrade to "cost unavailable" rather than erroring
- [ ] Cache reporting and prefix token-threshold warning become Anthropic-conditional

### Documentation (per CLAUDE.md sync rules)
- [ ] Update `skills/evaluate/references/eval-schema-reference.md` and SKILL.md for new
      provider fields
- [ ] `docs/cli-reference.md` and `docs/user-guide.md` provider sections
- [ ] README: update "Anthropic models" scoping language
- [ ] Adapter unit tests (suite is fully mocked — no API budget needed)

**Milestone**: `skillspar run suite.yaml` executes against an OpenAI-compatible endpoint
with tool-use tests and baseline comparison working, judge pinned to a fixed model.

## Phase 5D: Public Launch

Flip the repo public. Install paths (`pip install git+...`, plugin marketplace add) already
work against the GitHub repo — PyPI is deferred to post-launch.

- [ ] Decide history strategy: squash `main` to a single "Initial public release" commit
      (orphan branch + force push keeps the repo URL, so install/marketplace links stay
      valid) — or keep history after a secrets scan
- [ ] Tag `v0.1.0` and create a GitHub Release
- [ ] Make the repo public
- [ ] Smoke-test both install paths from a clean environment
      (`pip install git+https://github.com/kynetyk-ai/skillspar.git` and
      `/plugin marketplace add kynetyk-ai/skillspar`)

**Milestone**: The repo is public, tagged, and both documented install paths work from a
clean environment.

## Phase 5E: Post-Launch — PyPI & Dogfooding

### PyPI distribution
- [ ] PyPI packaging and distribution (`hatch build` + trusted publisher)
- [ ] GitHub release automation: tag-triggered workflow to build and publish to PyPI
- [ ] Update README install instructions to `pip install skillspar`

### Dogfooding — skill eval in CI
Test the `/skillspar:evaluate` skill with Skillspar's own framework, wired into GitHub
Actions. Demonstrates the CI/CD integration story with a real skill and catches regressions
when the skill package changes.

- [ ] Develop eval suite for `/skillspar:evaluate` using the skill itself (interactive)
- [ ] Validate suite stability (2–3 iterations, reliable skill vs baseline separation)
- [ ] GitHub Actions workflow (`.github/workflows/skill-eval.yml`): runs eval suite on
      `skills/evaluate/**` path changes, with `workflow_dispatch` for manual triggers
- [ ] `ANTHROPIC_API_KEY` repository secret
- [ ] Artifact upload for eval results (JSON report + saved responses)
- [ ] CI/CD integration section in `docs/user-guide.md` referencing this repo's workflow
      as a real-world example

**Milestone**: `pip install skillspar` works from PyPI, and changes to the
`/skillspar:evaluate` skill package trigger an automated eval run in CI that serves as a
reference implementation for users.

## Phase 6: Analytics + Advanced (Future)

- [ ] Sample size estimator — recommend run counts for statistically significant steer measurement
- [ ] Analytics package — standardized reporting for skill vs. baseline comparison, cross-model steer analysis, and confidence intervals
- [x] Steer strength metric — quantify the delta between skill and baseline pass rates — *subsumed by Phase 4D (steer erosion detection, pass_rate_delta)*
- [x] Snapshot testing (golden trace diffing for tool call sequences) — *subsumed by Phase 4D (stored baselines & temporal diffing)*
- [x] Flakiness detection (run N times, report variance) — *done in Phase 1 (repeated runs + pass_threshold)*
- [ ] A/B model comparison (same skill across model versions — and, building on Phase 5C,
      across providers — does the steer hold?)
- [ ] Response caching for faster re-runs
- [x] Centralized config (consolidate env vars, CLI flags, YAML defaults, and .env into a unified config layer)
- [x] Structured logging (replace ad-hoc output with configurable log levels for debugging, execution traces, and CI diagnostics)
