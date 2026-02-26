# User Guide

## Contents

- [Installation and Setup](#installation-and-setup)
- [Evaluating Skills](#evaluating-skills)
- [Best Practices](#best-practices)
- [Design Decisions](#design-decisions)
- [Frequently Asked Questions](#frequently-asked-questions)

**See also:** [CLI Reference](cli-reference.md) | [Examples Guide](examples.md)

## Installation and Setup

### Plugin

The plugin provides the `/skillspar:evaluate` skill inside Claude Code:

```bash
# From the Claude Code prompt
/plugin marketplace add kynetyk-ai/skillspar
/plugin install skillspar@kynetyk-tools
```

### CLI

The CLI runs generated test suites against the Anthropic API:

```bash
pip install git+https://github.com/kynetyk-ai/skillspar.git
```

For development mode (from a local clone):

```bash
claude --plugin-dir ./path/to/skillspar   # plugin
pip install -e ".[dev]"                     # CLI + dev deps
```

### API key

Skillspar needs an `ANTHROPIC_API_KEY` to make API calls. Set it in a `.env` file at the project root or export it in your shell:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

The plugin includes a `SessionStart` hook that checks whether the CLI is installed and the API key is set when you open Claude Code.

## Evaluating Skills

The workflow has three phases: **generate** a test suite, **run** it, and **analyze** the results.

### 1. Generate a suite

Run `/skillspar:evaluate` in Claude Code. Claude reads your `SKILL.md`, extracts testable behavioral claims, and collaborates with you to produce a `.eval.yaml` file. You approve the test plan before anything is written.

### 2. Run the suite

```bash
skillspar run my-skill.eval.yaml
```

Add `--verbose` for per-test detail including full model output and assertion results. Add `--output report.json` to save a structured JSON report for programmatic analysis.

```bash
# Verbose single suite
skillspar run my-skill.eval.yaml --verbose

# Run a directory of suites
skillspar run examples/ --verbose

# Save JSON report
skillspar run my-skill.eval.yaml --output report.json
```

### 3. Analyze results

The CLI prints a summary table with pass/fail counts and pass rates. With `--verbose`, you see each test's model output and which assertions passed or failed. With `baseline: true` enabled, you also see baseline pass rates — how the model performs without the skill — so you can measure marginal steer.

For JSON reports, the `/skillspar:evaluate` skill package includes helper scripts — `validate_eval.py` for schema validation and `parse_results.py` for readable result summaries — that Claude is instructed to use during the evaluate workflow.

For full CLI options, YAML schema, and assertion types, see the [CLI Reference](cli-reference.md). For annotated walkthroughs of every example suite, see the [Examples Guide](examples.md).

## Best Practices

**Read the skill first.** This sounds obvious, but it's easy to skip straight to `/skillspar:evaluate` and let Claude do the analysis. Read the SKILL.md yourself and form your own understanding of what behaviors matter before generating tests. This is especially important for third-party skills — external SKILL.md files and their references can contain malicious instructions disguised as legitimate skill content. The `/skillspar:evaluate` skill instructs Claude to flag suspicious content, but that should never be your only line of defense. Know what you're testing.

**Collaborate with Claude on test design.** When `/skillspar:evaluate` presents its plan — extracted claims, proposed assertions, coverage strategy — review it carefully and push back where it doesn't match what you actually care about. Claude may misinterpret a claim, pick the wrong assertion type, or test a behavior you consider low-priority. The plan phase exists so you catch these before any API calls are made. A suite you've actively shaped will test what matters to you; one you rubber-stamped may not.

**Treat first runs as exploratory.** Test failures come from two sources: the skill doesn't steer well enough, or the test doesn't match reality (too strict, too vague, or testing the wrong thing). Both are valuable signals. Expect 2–3 iterations before a suite stabilizes — the first run surfaces gaps, subsequent runs refine assertions and skill text until the suite is a reliable measure.

**Make `llm_judge` criteria self-contained.** The judge model sees only the model's output and your criteria text. It does not see the skill definition, conversation prefix, or test context. Criteria like "follows the skill's format" will fail — describe the format explicitly.

**Use `baseline: true` by default.** Baseline comparison is the core value proposition: it tells you whether the skill actually changes behavior. If baseline and skill pass rates are similar, the test isn't targeting skill-specific behavior.

**Use ranges for `turn_count` and `tool_called_times`.** A single tool call typically costs two turns (call + confirmation). Use `min`/`max` instead of `exactly` unless you have a strong reason for exactness.

**Use clear inputs for conversation prefix tests.** An ambiguous input like "Hi there!" after a coding conversation may be interpreted as continuing the coding chat. Use inputs that clearly signal the skill's domain.

**Make prefix content completely unrelated to the skill.** The point of a conversation prefix is to test context dilution — whether the skill holds up when prior conversation pushes it out of the model's attention. If the prefix is topically related to the skill, it injects helpful context that steers the model in the right direction anyway, and you're no longer measuring the skill's contribution. Use something with zero topical overlap — a passage from an open-source novel, a discussion about an unrelated domain, anything that couldn't accidentally help.

**Run reliability tests after stabilization.** Once the suite passes consistently at `temperature: 0`, switch to `temperature: 0.7` with `runs: 5` and `pass_threshold: 0.8` to measure consistency under realistic conditions.

## Design Decisions

**Why baseline comparison.** A skill test that passes doesn't tell you much if the model would pass it anyway. Baseline comparison (`baseline: true`) runs each test with and without the skill injected. The difference is the skill's marginal steer — the behavior the skill actually causes. This is the metric that matters when you're editing a skill and want to know if your change improved things.

**Why `skill_position` top vs bottom.** `skill_position: top` places the skill before the conversation prefix, so the prefix dilutes it — this is the harder test and the default. `skill_position: bottom` places the skill right before the test input, simulating a skill activated mid-conversation. Testing both positions tells you how robust the skill is to context dilution.

**Why `skill_only` exists.** Some tests include reference data that only makes sense with the skill (e.g., a list of valid greetings the skill defines). Marking those messages `skill_only: true` strips them from baseline runs, so the baseline isn't unfairly boosted by skill-specific context.

**Why we model skill injection as a user message.** In real agent environments, skills are injected into the conversation as text — not as system prompts or fine-tuned weights. Skillspar mirrors this: the skill body is wrapped in a user message (`"The following skill has been activated for this task: ..."`) and placed into the message array. This matches how Claude Code, Cursor, and similar agents actually deliver skills to the model, so test results reflect real-world steer.

**Why reference material uses synthetic tool calls.** When a skill mentions reference files, the agent typically reads them with tool calls before responding. Skillspar simulates this: context files declared in the `.eval.yaml` are injected as synthetic `Read` tool calls with tool results containing the file contents. This means the model sees reference material the same way it would in a real session — as tool output it "requested" — rather than as unexplained text appearing in the conversation.

**Why declarative YAML over programmatic tests.** YAML suites are reproducible, diffable, and versionable. You can review a test suite in a PR, diff it against a snapshot, or hand it to someone who has never seen the framework. Programmatic test frameworks offer more flexibility but make it harder to reason about what's being tested and whether it changed.

**Extensibility to other providers and agents.** Skillspar currently targets Anthropic models via the Messages API, but the underlying pattern — injecting instructional text into model context to specialize behavior — is not Anthropic-specific. Any agent compatible with the [Agent Skills open standard](https://agentskills.io/home) that follows a similar skill injection paradigm (Windsurf, Cursor, etc.) could be tested with the same approach. The engine would need a different API adapter and possibly different message assembly, but the declarative suite format, assertion types, and baseline methodology are provider-agnostic. If you're interested in extending Skillspar to another provider or agent — fork it, try it, and open a PR.

## Frequently Asked Questions

**My test passes without the skill too.**
The behavior you're testing isn't skill-specific — the base model does it on its own. Either the skill's steer on this behavior is weak, or the assertion isn't targeting what makes the skill unique. Look at the baseline pass rate to confirm, then either strengthen the skill or test a more distinctive behavior.

**The judge fails but the output looks correct.**
The judge criteria probably reference context the judge can't see. Check that your criteria describe the expected behavior completely without relying on the skill definition, conversation prefix, or test input. "Follows the skill's format" fails; "contains exactly three greetings, one per line, in English/Spanish/Japanese order" succeeds.

**My multi-turn test uses more turns than expected.**
A tool call followed by a confirmation message counts as two turns, not one. If you expect a read-then-write workflow, that's at minimum two tool calls = four turns. Use `turn_count min/max` ranges to accommodate this.

**Conversation prefix overwhelms the skill.**
This is the intended stress test — context dilution is real. If the skill can't hold up, try clearer test inputs that unambiguously signal the skill's domain. You can also test with `skill_position: bottom` to place the skill closer to the input. If it still fails, the skill text may need strengthening.

**How much does a run cost?**
Each test makes one or more API calls (skill run + optional baseline + optional judge). Multi-turn tests and reliability runs (`runs: 5`) multiply this. Use `enable_caching: true` when running the same prefix across multiple tests — prompt caching reduces cost for shared prefixes. Check your Anthropic dashboard for exact usage.

**Does Skillspar test automatic skill loading?**
No. Skillspar tests the skill's behavioral steer — what happens when the skill is active — not whether the agent loads the skill automatically. Automatic skill loading (matching a user query to the right skill file) is in our experience the least reliable aspect of skill systems, and it varies across agents. If you want a skill to be used reliably, instruct the agent to use it unambiguously (e.g., `/skillspar:evaluate` or 'Activate <my-skill>, then ...') rather than relying on automatic activation. Skillspar assumes the skill is already loaded and focuses on measuring what it does from there.

---

- [Examples Guide](examples.md) — annotated walkthrough of every example suite
- [CLI Reference](cli-reference.md) — full YAML schema, CLI options, and assertion types
