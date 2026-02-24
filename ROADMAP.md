# Roadmap

## Phase 1: Foundation — Single-Turn Tests

Core infrastructure for running single-turn eval suites.

- [ ] Pydantic config schema (minimal subset: suite metadata, single-turn tests, basic assertions)
- [ ] SKILL.md parser (YAML frontmatter extraction + body content)
- [ ] Conversation builder (YAML messages to Anthropic API message format)
- [ ] Trace data model (captures API response, tool calls, token usage)
- [ ] SingleTurnExecutor (one `messages.create()` call, returns Trace)
- [ ] Basic assertions: `tool_called`, `tool_not_called`, `output_contains`, `output_matches_regex`, `stop_reason`
- [ ] Console reporter (Rich-based pass/fail output)
- [ ] CLI entry point: `skill-eval run <file.yaml>`
- [ ] Working example suite with a synthetic test skill

**Milestone**: `skill-eval run examples/basic.eval.yaml` produces pass/fail output.

## Phase 2: Multi-Turn + Mock Responses

Agentic loop execution with scripted tool responses.

- [ ] Built-in tool schemas (Read, Write, Edit, Bash, Glob, Grep)
- [ ] Tool response matcher (match by tool name, JSONPath on args, wildcards)
- [ ] Response sequences (different responses for repeated calls to same tool)
- [ ] MultiTurnExecutor (loop: API call → match tool calls → inject responses → repeat)
- [ ] Extended assertions: `tool_sequence`, `tool_called_times`, `tool_args_match`, `turn_count`
- [ ] Suite defaults with per-test overrides (model, max_tokens, temperature)

**Milestone**: Multi-turn eval suites with scripted tool responses execute correctly.

## Phase 3: LLM Judge + CI Integration

Quality assertions and CI-friendly output formats.

- [ ] `llm_judge` assertion type (separate API call with criteria + threshold)
- [ ] JSON structured report output
- [ ] JUnit XML report output
- [ ] Token counting and cost estimation in reports
- [ ] CLI flags: `--format`, `--output`, `--filter`, `--model`, `--verbose`
- [ ] Parallel test execution with asyncio

**Milestone**: `skill-eval run suite.yaml --format junit --output results.xml` works in CI.

## Phase 4: Claude Code Skill — Test Design Assistant

A SKILL.md that guides Claude Code through test design.

- [ ] `/evaluate-skill` skill that analyzes a target SKILL.md
- [ ] Automated test scenario proposal
- [ ] `.eval.yaml` generation from skill analysis
- [ ] CLI result interpretation and feedback loop
- [ ] PyPI packaging and distribution
- [ ] Example suites for real-world skills
- [ ] Documentation

**Milestone**: `/evaluate-skill my-skill/SKILL.md` generates a starter test suite.

## Phase 5: Advanced (Future)

- [ ] Snapshot testing (golden trace diffing)
- [ ] Flakiness detection (run N times, report variance)
- [ ] A/B model comparison
- [ ] Auto-generate test suites from SKILL.md using LLM
- [ ] Response caching for faster re-runs
