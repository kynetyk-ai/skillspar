# Skillspar CLI Reference

Full reference for `.eval.yaml` test suite configuration, CLI commands, and result interpretation.

## Contents

- [Configuration Defaults](#configuration-defaults)
- [Environment Variables](#environment-variables)
- [Test Suite Format](#test-suite-format)
- [Baseline Testing](#baseline-testing)
- [Mid-Conversation Testing](#mid-conversation-testing)
- [Repeated Runs & Reliability](#repeated-runs--reliability)
- [Running Tests](#running-tests)
- [Watch Mode](#watch-mode)
- [Snapshots](#snapshots)
- [Architecture](#architecture)
- [Interpreting Results](#interpreting-results)
- [Iterative Refinement Workflow](#iterative-refinement-workflow)

**See also:** [User Guide](user-guide.md) | [Examples Guide](examples.md)

## Configuration Defaults

All defaults can be overridden in the `defaults` block of your `.eval.yaml` or per-test:

| Field | Default | Description |
|-------|---------|-------------|
| `provider` | `anthropic` | API provider: `anthropic` or `openai` (any OpenAI-compatible endpoint) |
| `base_url` | none | API base URL override, for OpenAI-compatible endpoints (OpenRouter, LiteLLM, Ollama, vLLM) |
| `api_key_env` | none | Custom environment variable name for the API key |
| `model` | `claude-sonnet-4-5-20250929` | Model for test runs |
| `judge_provider` | none (same as `provider`) | Provider for `llm_judge` assertions — pin the judge to a fixed provider when comparing a skill across providers |
| `judge_model` | `""` (same as `model`) | Model for `llm_judge` assertions; **required** when `judge_provider` differs from `provider` |
| `system_prompt` | `""` | System prompt providing a constant persona for both skill and baseline runs |
| `max_tokens` | `4096` | Max tokens per API response |
| `temperature` | `0` | Sampling temperature |
| `runs` | `1` | Times to repeat each test |
| `pass_threshold` | `1.0` | Fraction of runs that must pass |
| `concurrency` | `1` | Max parallel API calls |
| `max_retries` | `2` | API retry attempts on transient failure |
| `max_turns` | `10` | Turn limit for multi-turn tests |
| `enable_caching` | `true` | Enable prompt caching for shared prefixes and system prompts (Anthropic only) |

### Providers

The default provider is Anthropic. Setting `provider: openai` (or passing `--provider openai`) runs the suite against any endpoint speaking the OpenAI Chat Completions API — OpenAI itself, or OpenRouter / LiteLLM / Ollama / vLLM via `base_url`. Requires the optional dependency: `pip install "skillspar[openai]"`.

```yaml
defaults:
  provider: openai
  base_url: "http://localhost:11434/v1"   # e.g. Ollama
  model: "llama3.1"
  judge_provider: anthropic                # keep quality judging on a fixed model
  judge_model: "claude-sonnet-4-5-20250929"
```

Provider notes:

- **Stop reasons** are normalized — write `stop_reason` assertions with either vocabulary (`end_turn`/`stop`, `tool_use`/`tool_calls`, `max_tokens`/`length`).
- **Prompt caching** (`enable_caching`, cache cost reporting) is Anthropic-only; OpenAI-compatible endpoints cache automatically and `cache_control` markers are stripped.
- **Cost estimation** covers Claude models out of the box; add entries for other models via `SKILLSPAR_PRICING_FILE` (set `"cache_semantics": "openai"` on those entries). Unknown models report no cost rather than erroring.
- The adapter sends `max_tokens` (not `max_completion_tokens`) for widest compatible-server support; the very newest OpenAI models may reject it.

## Environment Variables

Skillspar reads a `.env` file at the working directory (via `python-dotenv`) and the process environment. Shell exports take precedence over `.env`. See `.env.example` for a ready-to-copy template.

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | yes* | API key for the `anthropic` provider (default) |
| `OPENAI_API_KEY` | yes* | API key for the `openai` provider (*whichever provider a suite uses; override the var name with `api_key_env`) |
| `SKILLSPAR_MODEL` | no | Default model when the suite `defaults` block doesn't set one |
| `SKILLSPAR_JUDGE_MODEL` | no | Default model for `llm_judge` assertions (falls back to the test model) |
| `SKILLSPAR_PROVIDER` | no | Default provider (`anthropic` or `openai`) when the suite doesn't set one |
| `SKILLSPAR_BASE_URL` | no | Default API base URL for OpenAI-compatible endpoints |
| `SKILLSPAR_JUDGE_PROVIDER` | no | Default judge provider when the suite doesn't set one |
| `SKILLSPAR_OUTPUT` | no | Directory for auto-named JSON reports; the `--output` flag overrides with an exact path |
| `SKILLSPAR_LOG_LEVEL` | no | Logging verbosity: `DEBUG`, `INFO`, `WARNING` (default), `ERROR` |
| `SKILLSPAR_PRICING_FILE` | no | Path to a JSON file of model pricing entries, merged over the builtin table. Each entry: `{"<model-id>": {"input": <$/Mtok>, "output": <$/Mtok>, "cache_write_multiplier": 1.25, "cache_read_multiplier": 0.1}}` |
| `SKILLSPAR_SNAPSHOT_DIR` | no | Snapshot storage directory (default `.skillspar/snapshots/`); the `--snapshot-dir` flag overrides |

Precedence for values that appear in multiple places: CLI flags > `.eval.yaml` > environment variables > builtin defaults.

## Test Suite Format

A `.eval.yaml` file defines a test suite:

```yaml
suite: "my skill basics"          # suite name
skill: "./my-skill/SKILL.md"     # path to skill file

context:                          # optional: files injected into all tests
  - file: "./src/utils.py"
  - file: "./src/main.py"
    lines: [10, 25]              # only lines 10–25 (1-indexed)

defaults:                         # override configuration defaults
  model: "claude-sonnet-4-5-20250929"
  max_tokens: 4096
  temperature: 0

tools:                            # tool schemas available to the model
  - builtin: Read
  - builtin: Write

tests:                            # one or more test cases
  - name: "responds correctly"
    type: single_turn             # or multi_turn
    input:
      messages:
        - role: user
          content: "Hello!"
    assertions:
      - type: output_contains
        value: "Hello"
```

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

`llm_judge` assertions require a `criteria` string describing what to evaluate. Set `model` per-assertion or `judge_model` in suite defaults to use a different model as the evaluator.

### Mock Tools

Built-in schemas for common Claude Code tools:

```yaml
tools:
  - builtin: Read
  - builtin: Write
  - builtin: Edit
  - builtin: Bash
  - builtin: Glob
  - builtin: Grep
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

### Tool Responses

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

Use `responses` (array) to cycle through different results on successive calls to the same tool:

```yaml
tool_responses:
  - match: { tool: Read }
    responses:
      - { content: "# First file" }
      - { content: "# Second file" }   # used on 2nd+ call
```

### Context Files

Inject file contents as user messages to simulate file discovery. Available at suite level (applies to all tests) and per-test:

```yaml
# Suite-level context — injected into every test
context:
  - file: "./src/utils.py"
  - file: "./src/main.py"
    lines: [10, 25]     # only lines 10–25 (1-indexed)

tests:
  - name: "handles edge case"
    context:             # test-level context — this test only
      - file: "./fixtures/edge-case.txt"
    # ...
```

## Baseline Testing

The `baseline: true` flag runs every test twice — once with your skill injected, once without. If the baseline passes at the same rate as the skill, your skill isn't adding value. If the skill passes 5/5 and baseline passes 1/5, you've proven the skill is doing real work.

```yaml
tests:
  - name: "always reads before writing"
    type: multi_turn
    baseline: true    # also run without the skill prompt
    runs: 5           # repeat for statistical confidence
    # ...
```

Messages marked `skill_only: true` are excluded from baseline runs. This lets you inject skill-specific reference material (e.g. a schema document the skill tells the model to consult) without inflating the baseline:

```yaml
tests:
  - name: "uses schema reference"
    baseline: true
    input:
      messages:
        - role: user
          content: "Here is the schema reference: ..."
          skill_only: true   # stripped from baseline runs
        - role: user
          content: "Generate a config file following the schema"
    # ...
```

## Mid-Conversation Testing

In real usage, a skill may be injected at the start of a conversation and needed many turns later, or injected just before use. The `conversation_prefix` field prepends a simulated prior conversation before your test input, and `skill_position` controls where the skill appears relative to it:

- `top` (default) — skill is injected **before** the prefix, simulating early injection followed by unrelated context (worst-case dilution)
- `bottom` — skill is injected **after** the prefix, simulating just-in-time injection (more favorable)

```yaml
conversation_prefix:
  skill_position: top   # or bottom
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

Test both positions to measure how sensitive your skill is to context dilution.

## Repeated Runs & Reliability

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

## Running Tests

### CLI Options

The `run` command accepts these flags (all optional — YAML defaults apply when omitted):

```
skillspar run [OPTIONS] EVAL_FILES...

  --runs N             Override runs per test
  --concurrency N      Max parallel API calls
  --output PATH        Write report to file
  --format json|junit  Report format (default: inferred from extension, or json)
  --filter PATTERN     Only run tests whose name contains this substring
  --model MODEL        Override the suite default model
  --provider NAME      Override the suite default provider (anthropic|openai)
  --base-url URL       Override the API base URL (OpenAI-compatible endpoints)
  --verbose            Show per-assertion details
  --log-level LEVEL    Set logging verbosity (DEBUG/INFO/WARNING/ERROR)
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

A failure in one suite does not abort others.

## Watch Mode

Watch the eval file, skill file, and all referenced context files — re-run automatically on any change:

```bash
skillspar watch suite.eval.yaml
skillspar watch suite.eval.yaml --filter "greeting" --verbose --debounce 500
```

Each iteration diffs against the previous run, highlighting regressions and improvements. Supports the same `--runs`, `--concurrency`, `--filter`, `--model`, `--provider`, `--base-url`, `--verbose`, and `--log-level` flags as `run`, plus `--debounce` (ms, default: 300).

## Snapshots

Save test results as snapshots and diff them to track progress over time:

```bash
# Save a snapshot after running a suite
skillspar snapshot save my-skill.eval.yaml

# List saved snapshots (optionally filter by suite name)
skillspar snapshot list
skillspar snapshot list --suite "greeting skill"

# Diff two saved snapshots
skillspar snapshot diff before.json after.json

# Run a suite, diff against the most recent snapshot, and save the new result
skillspar snapshot diff --latest my-skill.eval.yaml
```

## Architecture

SKILL.md is injected as a user message — matching how Claude Code delivers skills to the agent. An optional `system_prompt` in suite defaults provides a constant persona for both skill and baseline runs. Mock tools are defined with Anthropic tool schemas (translated automatically for OpenAI-compatible providers). The API response is inspected against your assertions.

```
YAML Config → Skill Parser → Test Executor → Assertion Engine → Reporter
                                    ↑
                               Tool Registry
                           (mock definitions +
                            scripted responses)
```

### Executor Modes

- **SingleTurnExecutor** — One API call, assert on response. Use for unit-testing individual behaviors.
- **MultiTurnExecutor** — Agentic loop with scripted tool responses until completion or turn limit (`max_turns`, default: 10). Use for testing that a skill drives the right tool calls in the right order.

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

## Iterative Refinement Workflow

1. **Start with `/skillspar:evaluate`** to generate an initial test suite from your SKILL.md.
2. **Run the suite** with `skillspar run` — identify which tests fail and why.
3. **Tighten flaky tests**: If a test passes inconsistently, increase `runs` and set an appropriate `pass_threshold`. Use `llm_judge` instead of brittle substring assertions for subjective quality.
4. **Add baseline**: Enable `baseline: true` on key tests to confirm your skill adds value beyond the model's default behavior.
5. **Use watch mode** during active development: `skillspar watch suite.eval.yaml` re-runs on every save.
6. **Snapshot and diff** to track progress: `skillspar snapshot diff --latest suite.eval.yaml` shows what changed between runs.
7. **Run all suites** before merging: `skillspar run examples/` validates the full skill library.
