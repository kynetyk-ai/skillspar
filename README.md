# Skill Evaluator

Declarative testing harness for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) Agent Skills.

Define expected behaviors in YAML. Run them against the Anthropic API. Get reproducible pass/fail results.

## The Problem

When developing Claude Code Agent Skills (SKILL.md packages), testing is manual: invoke the skill, eyeball the output, repeat. There's no systematic way to verify that a skill produces the intended behavior, track regressions, or run checks in CI.

## The Solution

Skill Evaluator lets you write declarative test suites in `.eval.yaml` files that specify:
- What **messages** to send (conversation scenarios)
- What **tools** the skill has access to (mock schemas with scripted responses)
- What **assertions** to check (tool calls, output content, argument patterns, LLM-judged quality)

The CLI executes these suites against the Anthropic API directly — no Claude Code runtime needed — and reports results.

## Quick Start

```bash
pip install skill-evaluator
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
skill-eval run my-skill.eval.yaml
```

## How It Works

### Two-Phase Workflow

**Phase A: Test Design** — You and Claude Code collaborate to analyze a skill, identify key behaviors, design mock tools, craft conversation scenarios, and define assertions. Output: a `.eval.yaml` file.

**Phase B: Test Execution** — The CLI runs the suite reproducibly: same config, same API calls, same assertions every time. Captures token counts, costs, latencies, pass/fail rates.

### Architecture

The skill's SKILL.md becomes the `system` prompt. Mock tools are standard Anthropic tool definitions. Conversation history is the `messages` array. The API response is inspected against your assertions.

```
YAML Config → Skill Parser → Test Executor → Assertion Engine → Reporter
                                    ↑
                               Tool Registry
                           (mock definitions +
                            scripted responses)
```

### Executor Modes

- **SingleTurnExecutor** — One API call, assert on response. Use for unit-testing individual behaviors.
- **MultiTurnExecutor** — Agentic loop with scripted mock tool responses until completion or turn limit. Use for integration-testing complex workflows.

## Test Definition Format

See [`examples/basic.eval.yaml`](examples/basic.eval.yaml) for a complete example.

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

## Development

```bash
git clone <repo-url>
cd skill-evaluator
pip install -e ".[dev]"
pytest
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the phased implementation plan.

## License

MIT
