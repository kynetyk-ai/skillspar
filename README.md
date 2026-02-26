# Skillspar: Quantitative Testing Harness for Agent Skills

Define test scenarios in YAML, run them against the API, and measure whether your skill actually changes model behavior — or whether it's just context bloat.

Skillspar provides baseline comparison to quantify the "steer" your skill provides, repeated runs for statistical confidence, and multi-turn tool mocking for agentic workflows. Currently tests against the [Anthropic API](https://docs.anthropic.com/en/docs/api-reference), extensible to other providers.

## Background

Agent Skills promise to turn general-purpose, tool-using agents into specialists for a specific task — without fine-tuning or custom code. A well-designed skill has potential to make a smaller model match frontier-model behavior on a specific task, offering significant cost savings if the steer can be confirmed. And because skills are just prompt documents, they're arguably the most accessible path to rapid agent specialization.

Despite this potential, best practices for skill creation rely on intuition. Testing is manual if it happens at all: invoke the skill, eyeball the output, repeat. There are no quantitative tools for measuring the impact of skills on agent behavior — even on a relative basis. This makes it difficult to trust skills in production because fundamental questions go unanswered:

- **Does this skill reliably steer behavior?** Does the model follow the skill's instructions, or would it behave the same without them?
- **Is this skill worth the context?** If the model already behaves correctly without the skill, it's dead weight.
- **Can this skill close the gap between models?** Could a cheaper model with the right skill match a frontier model on this task?
- **Did a change break anything?** After editing a skill or after a model update, there's no regression test — just hope.

## The Solution

Many modern tool-using agents inject skills as user-role messages. Skillspar replicates this as part of the testing paradigm: it injects SKILL.md as a user message in simulated conversations, models file discovery via synthetic tool calls, and asserts on the resulting behavior.

If the skill can't steer in isolation, it won't steer inside the full agent either.

Skillspar provides a declarative test harness — `.eval.yaml` files that specify:
- **messages** defining conversational scenarios
- **tools** the skill has access to (mock schemas with scripted responses)
- **assertions** on the behaviors under test (tool calls, output content, argument patterns, sequences)

The CLI executes suites against the Anthropic API and reports results. The architecture is provider-agnostic and can be extended to any LLM API that supports tool use.

### Baseline Comparison: Prove Your Skill Matters

The `baseline: true` flag runs every test twice — once with your skill injected, once without. If the baseline passes at the same rate as the skill, your skill isn't adding value. If the skill passes 5/5 and baseline passes 1/5, you've proven the skill is doing real work.

```yaml
tests:
  - name: "always reads before writing"
    type: multi_turn
    baseline: true    # also run without the skill prompt
    runs: 5           # repeat for statistical confidence
    # ...
```

### Mid-Conversation Testing: Survive Context Dilution

Skills are injected early in a conversation, but real usage buries them under turns of unrelated context. The `conversation_prefix` field prepends a simulated prior conversation before your test input, so you can measure whether the skill still steers after dilution.

```yaml
conversation_prefix:
  messages:
    - role: user
      content: "Can you help me refactor this function?"
    - role: assistant
      content: "Sure! Could you share the function?"
    # ... more turns of unrelated conversation

tests:
  - name: "skill activates after prior context"
    baseline: true
    # ...
```

Use `skill_position` to control where the skill is injected relative to the prefix — `top` (default) places the skill before the prefix to simulate maximum dilution, `bottom` places it after for a more favorable test.

## Installation

### As a Claude Code Plugin

Install the `/evaluate-skill` skill directly into Claude Code:

```bash
# Development mode (from a clone of this repo)
claude --plugin-dir ./path/to/skillspar
```

Then install the CLI to run generated test suites:

```bash
pip install git+https://github.com/kynetyk-ai/skillspar.git
```

### As a Python Package

```bash
pip install git+https://github.com/kynetyk-ai/skillspar.git
```

## Quick Start

```bash
pip install git+https://github.com/kynetyk-ai/skillspar.git
```

Create a test suite (`my-skill.eval.yaml`):

```yaml
suite: "greeting skill basics"
skill: "./greeting/SKILL.md"

defaults:
  model: "claude-sonnet-4-5-20250929"
  max_tokens: 4096
  temperature: 0

tests:
  - name: "responds with greeting"
    type: single_turn
    input:
      messages:
        - role: user
          content: "Hello!"
    assertions:
      - type: output_contains
        value: "Hello"
```

Run it:

```bash
skillspar run my-skill.eval.yaml
```

### Multi-Suite Execution

Run all eval suites in a directory, or pass multiple files and globs:

```bash
# Run all eval files in a directory (recursive)
skillspar run examples/

# Run specific files
skillspar run greet.eval.yaml review.eval.yaml

# Mix files and directories
skillspar run greet.eval.yaml examples/advanced/

# Write a combined report
skillspar run examples/ --output results.json
```

When multiple suites are discovered, skillspar runs each sequentially and prints an aggregated dashboard:

```
Multi-Suite Summary

 Suite                      Status  Tests   Cost
 greeting skill basics      PASS    4/4     $0.12
 code review skill          FAIL    7/9     $0.85
 mid-conversation tests     PASS    3/3     $0.23

3 suites: 1 failed, 2 passed
Total cost: $1.20
```

A failure in one suite does not abort others. Exit codes: 0 = all pass, 1 = any test failures, 2 = any config/validation errors (takes priority over 1).

### Repeated Runs & Reliability

Run each test multiple times to measure consistency and compare against baseline:

```bash
skillspar run my-skill.eval.yaml --runs 10 --concurrency 4 --output results.json
```

```yaml
defaults:
  runs: 5              # run each test 5 times
  pass_threshold: 0.8  # pass if >= 80% of runs pass
  concurrency: 4       # max parallel API calls

tests:
  - name: "critical behavior"
    type: single_turn
    baseline: true      # also run without skill — prove the skill adds value
    # ...
```

## How It Works

### Architecture

SKILL.md is injected as a user message at the start of the conversation — matching how real skill loaders (Claude Code, Cursor, Windsurf) deliver skills. An optional `system_prompt` in suite defaults provides a constant persona for both skill and baseline runs. Mock tools use standard Anthropic tool definitions. The API response is inspected against your assertions.

```
YAML Config → Skill Parser → Test Executor → Assertion Engine → Reporter
                                    ↑
                               Tool Registry
                           (mock definitions +
                            scripted responses)
```

### Executor Modes

- **SingleTurnExecutor** — One API call, assert on response. Use for unit-testing individual behaviors.
- **MultiTurnExecutor** — Agentic loop with scripted tool responses until completion or turn limit. Use for testing that a skill drives the right tool calls in the right order.

## Test Definition Format

See [`examples/basic.eval.yaml`](examples/basic.eval.yaml) for a complete example and [`examples/reliability.eval.yaml`](examples/reliability.eval.yaml) for repeated runs with baseline comparison.

### Assertion Types

| Type | Purpose |
|------|---------|
| `tool_called` / `tool_not_called` | Was a tool used (or not)? |
| `tool_called_times` | Call count (min/max/exactly) |
| `tool_args_match` | JSONPath query on tool arguments |
| `tool_sequence` | Tools called in a specific order |
| `output_contains` / `output_not_contains` | Substring in final text |
| `output_matches_regex` | Regex on final text |
| `llm_judge` | Separate LLM call to evaluate quality |
| `stop_reason` | Assert end_turn vs tool_use vs max_tokens |
| `turn_count` | Number of turns in multi-turn test |

### Mock Tools

Use built-in schemas for common Claude Code tools:

```yaml
tools:
  - builtin: Read
  - builtin: Write
```

Or define custom schemas:

```yaml
tools:
  - name: search_docs
    description: "Search documentation"
    input_schema:
      type: object
      properties:
        query: { type: string }
      required: ["query"]
```

For multi-turn tests, script tool responses with pattern matching:

```yaml
tool_responses:
  - match: { tool: Write }
    response: { content: "File written successfully" }
  - match: { tool: Read, args: { "$.file_path": "*.md" } }
    response: { content: "# Document content" }
  - match: "*"
    response: { content: "OK" }
```

## Interpreting Results

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tests passed |
| 1 | One or more tests failed |
| 2 | Configuration or validation error (bad YAML, missing skill file, no matching tests) |

In multi-suite runs, exit code 2 takes priority over 1 — if any suite has a config error, the run exits with 2 even if other suites had test failures.

### Reading Pass/Fail Output

Each test shows a pass/fail indicator and, for multi-run tests, the pass rate:

```
  ✓ responds with greeting
  ✗ follows formatting rules  3/5 passed (threshold: 80%)
    baseline: 1/5 passed
```

**Baseline interpretation**: If your skill passes 5/5 and baseline passes 1/5, the skill is doing real work. If both pass at similar rates, the skill may not be adding value.

### Iterative Refinement Workflow

1. **Start with `/evaluate-skill`** to generate an initial test suite from your SKILL.md.
2. **Run the suite** with `skillspar run` — identify which tests fail and why.
3. **Tighten flaky tests**: If a test passes inconsistently, increase `runs` and set an appropriate `pass_threshold`. Use `llm_judge` instead of brittle substring assertions for subjective quality.
4. **Add baseline**: Enable `baseline: true` on key tests to confirm your skill adds value beyond the model's default behavior.
5. **Use watch mode** during active development: `skillspar watch suite.eval.yaml` re-runs on every save.
6. **Snapshot and diff** to track progress: `skillspar snapshot diff --latest suite.eval.yaml` shows what changed between runs.
7. **Run all suites** before merging: `skillspar run examples/` validates the full skill library.

## Development

```bash
git clone https://github.com/kynetyk-ai/skillspar.git
cd skillspar
pip install -e ".[dev]"
pytest
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the phased implementation plan.

## License

[MIT](LICENSE)
