# Skillspar: Quantitative Testing Harness for Agent Skills

Define test scenarios in YAML, run them against the API, and measure how well your Agent Skill "steers" behavior — across edits, models, and context conditions.

## Why Test Skills?

Agent skills are prompt documents and reference materials that specialize general-purpose agents — no fine-tuning, no custom code. But measuring how well a skill performs is largely manual: invoke it, eyeball the output, track results by hand. There's no automated way to check whether an edit improved things, whether the skill holds up after context dilution, or whether a model update changed behavior. Skillspar fills the gap with a declarative test harness — define expected behaviors in YAML, run them against the API, and get quantitative results you can track over time. Skillspar currently evaluates steer on tool-using Anthropic models using API calls. 

The underlying pattern — injecting instructional text into model context to specialize behavior — is shared across major coding agents including [Claude Code](https://code.claude.com/docs/en/skills), [Cursor](https://docs.cursor.com/context/rules-for-ai), and [Windsurf](https://docs.windsurf.com/windsurf/cascade/memories), and is converging into an [open standard](https://openai.github.io/agent-skills-spec/).

## How It Works

Skillspar has two components designed to work together inside Claude Code:

1. **The plugin** (`/skillspar:evaluate`) — Claude reads your SKILL.md, analyzes its behaviors, and collaborates with you to generate a structured test suite (`.eval.yaml`).  This includes customizeable injection of the SKILL.md content in relation to simulated conversation context and simulated progressive discovery of reference material that inform behaviors modeled as tool call and tool result messages.
2. **The CLI** (`skillspar run`) — Claude executes the generated suite against the Anthropic API and reports quantitative results — pass rates, baseline comparisons, and cost.

The typical workflow:

1. Install the plugin and CLI (see below)
2. Run `/skillspar:evaluate` — Claude generates a `.eval.yaml` tailored to your skill
3. Run `skillspar run my-skill.eval.yaml` — the CLI executes the tests and reports results
4. Iterate: refine the suite, re-run, use watch mode and snapshots to track progress

## Installation

```bash
# 1. Install the plugin (provides /skillspar:evaluate)
/plugin marketplace add kynetyk-ai/skillspar
/plugin install skillspar@kynetyk-tools

# 2. Install the CLI (runs generated test suites)
pip install git+https://github.com/kynetyk-ai/skillspar.git
```

For development mode (from a clone of this repo):

```bash
# Install the CLI in editable mode (provides skillspar run, watch, snapshot)
pip install -e "~/path/to/skillspar[dev]"

# Load the plugin into Claude Code from your skill project
claude --plugin-dir ~/path/to/skillspar
```

## Quick Start

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

## Examples

The `examples/` directory contains numbered eval suites (`01` through `08`) that progressively demonstrate every feature of the framework — from basic output assertions through multi-turn tool loops, conversation prefixes, reliability runs, and advanced features like `system_prompt` and custom tools. They use a toy greeting skill to keep the focus on framework mechanics, not skill complexity. See the [Examples Guide](docs/examples.md) for what each file demonstrates and expected outcomes.

```bash
# Run a single example
skillspar run examples/01-basics.eval.yaml --verbose

# Run all examples
skillspar run examples/ --verbose
```

## Key Capabilities

- **Repeated runs** — run each test multiple times with `runs` and `pass_threshold` to measure consistency and build statistical confidence. See [Repeated Runs](docs/cli-reference.md#repeated-runs--reliability).

- **Watch mode** — `skillspar watch` monitors the eval file, skill file, and all referenced context files, re-running on any change and diffing against the previous iteration. See [Watch Mode](docs/cli-reference.md#watch-mode).

- **Baseline comparison** — `baseline: true` runs each test with and without the skill to quantify the skill's contribution. Messages marked `skill_only: true` are excluded from baseline runs, so you can include skill-specific reference material without inflating the baseline. As a side benefit, baseline testing can surface unexpected behavioral shifts introduced by third-party skills — a practical defense against [prompt injection in agent skill supply chains](https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/). See [Baseline Testing](docs/cli-reference.md#baseline-testing).

- **Mid-conversation testing** — `conversation_prefix` prepends simulated prior conversation, and `skill_position` (`top` or `bottom`) controls where the skill is injected relative to it — test worst-case dilution or just-in-time injection. See [Mid-conversation Testing](docs/cli-reference.md#mid-conversation-testing).

- **Snapshots** — save test results and diff them over time with `skillspar snapshot save`, `list`, and `diff` to track regressions and improvements. See [Snapshots](docs/cli-reference.md#snapshots).

- **Multi-suite execution** — pass directories, globs, or multiple files to `skillspar run` and get an aggregated dashboard. See [Multi-suite Execution](docs/cli-reference.md#multi-suite-execution).

- **LLM judge** — use a separate model call to evaluate subjective quality via `llm_judge` assertions, with configurable `criteria` and optional `judge_model`. See [Assertion Types](docs/cli-reference.md#assertion-types).

For the full YAML schema, all CLI options, assertion types, mock tool builtins, and configuration defaults, see the [CLI Reference](docs/cli-reference.md). For setup instructions, best practices, and design rationale, see the [User Guide](docs/user-guide.md).

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

Skillspar is maintained by [Kynetyk Holdings LLC](https://github.com/kynetyk-ai). For commercial licensing inquiries, contact hello@kynetyk.ai.
