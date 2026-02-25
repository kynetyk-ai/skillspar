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
- [x] Basic assertions: `tool_called`, `tool_not_called`, `output_contains`, `output_matches_regex`, `stop_reason`
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

## Phase 4: Automated Skill Analysis — `/evaluate-skill`

A SKILL.md that guides Claude Code through analyzing a target skill and generating a test suite. This is the key differentiator — no other tool can read a skill definition and automatically propose what to test, with baseline enabled by default so every generated suite answers "is this skill worth the context?"

- [ ] `/evaluate-skill` skill that analyzes a target SKILL.md
- [ ] Skill structure analysis: extract behavioral claims, tool-use patterns, examples, constraints
- [ ] Automated test scenario generation with baseline enabled by default
- [ ] `.eval.yaml` generation from skill analysis
- [ ] Assertion type guidance: auto-generator should propose `llm_judge` for subjective quality criteria (tone, naturalness, completeness) and deterministic assertions for structural behaviors (tool calls, sequences, output keywords). Documentation should advise users that `output_contains`/`output_matches_regex` are brittle proxies for subjective quality and will break across model updates.
- [ ] CLI result interpretation and feedback loop
- [ ] PyPI packaging and distribution
- [ ] Example suites for real-world skills that demonstrate measurable steer
- [ ] Documentation
- [ ] Re-evaluate README prior to final release

**Milestone**: `/evaluate-skill my-skill/SKILL.md` generates a starter test suite that proves whether the skill changes model behavior.

## Phase 5: Analytics + Advanced (Future)

- [ ] Sample size estimator — recommend run counts for statistically significant steer measurement
- [ ] Analytics package — standardized reporting for skill vs. baseline comparison, cross-model steer analysis, and confidence intervals
- [ ] Steer strength metric — quantify the delta between skill and baseline pass rates
- [ ] Snapshot testing (golden trace diffing for tool call sequences)
- [x] Flakiness detection (run N times, report variance) — *done in Phase 1 (repeated runs + pass_threshold)*
- [ ] A/B model comparison (same skill across model versions — does the steer hold?)
- [ ] Response caching for faster re-runs
- [ ] Centralized config (consolidate env vars, CLI flags, YAML defaults, and .env into a unified config layer)
- [ ] Structured logging (replace ad-hoc output with configurable log levels for debugging, execution traces, and CI diagnostics)
