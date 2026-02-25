# Skillspar: Quantitative Testing Harness for Agent Skills

Define test scenarios in YAML, run them against the API, and measure whether your skill actually changes model behavior — or whether it's just context bloat. Skillspar includes baseline comparison to quantify the steer your skill provides, repeated runs for statistical confidence, and multi-turn tool mocking for agentic workflows. Currently tests against the [Anthropic API](https://docs.anthropic.com/en/docs/api-reference), extensible to other providers.

## Background

Agent Skills promise to turn a general-purpose, conversational, tool-using agent into a specialist for a specific task or workflow — without fine-tuning, custom code, or the bespoke systems of hooks and prompt engineering that differentiate one coding agent from another. Skills can be written without coding skills, making them arguably the most accessible path to rapid agent specialization.

Despite this potential, best practices for skill creation are defined largely by gestalt and intuition. Testing is manual if performed at all: invoke the skill, eyeball the output, repeat. There are no quantitative tools for measuring whether a skill actually steers behavior — even on a relative basis. This makes it difficult for enterprises and users to trust skills in production or feel confident they provide more than context bloat.

The stakes are real. A well-designed skill may be sufficient to make a smaller model behave like a frontier model for a specific task — a significant cost savings if the steer can be confirmed. But without measurement, there's no way to answer the fundamental questions:

- **Does this skill reliably steer behavior?** Does the model follow the skill's instructions, or would it do the same thing without them?
- **Is this skill worth the context?** If the model already behaves correctly without the skill, it's dead weight in the system prompt.
- **Can this skill close the gap between models?** Could a cheaper model with the right skill match a frontier model's behavior on this task?
- **Did my change break anything?** After editing a skill, there's no regression test — just hope.

## The Solution

Skillspar works on a basic premise: modern coding agents inject Agent Skills into a variable system prompt framework that we can't fully observe or replicate. But we can isolate the steer a skill provides by injecting its SKILL.md as part of a system prompt in simulated conversations, modeling context file discovery via synthetic tool-call messages, and asserting on the resulting behavior.

If the skill can't steer in isolation, it won't steer inside the full agent either.

Based on this premise, Skillspar provides a declarative test harness — `.eval.yaml` files that specify:
- **messages** that define conversational scenarios where Agent Skills should be invoked 
- **tools** the skill has access to (mock schemas with scripted responses)
- **assertions** on behaviors under test (tool calls, output content, argument patterns, sequences)

The CLI currently executes these suites against the Anthropic API directly and reports results. While the current implementation is designed for use with the Anthropic API, there is no fundamental reason the harness could not be extended to test LLMs from other providers that support Agent Skills.

### Baseline Comparison: Prove Your Skill Matters

The `baseline: true` flag runs every test twice — once with your skill as the system prompt, once without. This gives you a concrete, quantitative answer: if the baseline passes at the same rate as the skill, your skill isn't adding value. If the skill passes 5/5 and baseline passes 1/5, you've proven the skill is doing real work.

```yaml
tests:
  - name: "always reads before writing"
    type: multi_turn
    baseline: true    # also run without the skill prompt
    runs: 5           # repeat for statistical confidence
    # ...
```

## Quick Start

```bash
pip install skillspar
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
- **MultiTurnExecutor** — Agentic loop with scripted mock tool responses until completion or turn limit. Use for testing that a skill causes the model to call the right tools in the right order.

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
