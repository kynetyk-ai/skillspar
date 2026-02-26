# Examples Guide

## Contents

- [Running](#running)
- [Examples](#examples)
- [Feature coverage](#feature-coverage)

**See also:** [User Guide](user-guide.md) | [CLI Reference](cli-reference.md)

The `examples/` directory contains a progressive set of numbered eval suites that demonstrate every functional mode of the Skillspar evaluation framework. They are intentionally simple — each uses a toy greeting skill to isolate and showcase specific features. They are not meant to replace real test packages or simulate production skill evaluation.

All numbered examples use the same `sample-skill/SKILL.md` — a multilingual greeting skill that responds in English, Spanish, and Japanese. A separate `code-review-skill.eval.yaml` is included as a real-world companion.

## Running

```bash
# Run a single example
skillspar run examples/01-basics.eval.yaml --verbose

# Run all examples
skillspar run examples/ --verbose

# Save a JSON report
skillspar run examples/01-basics.eval.yaml --verbose --output report.json
```

## Examples

### 01-basics.eval.yaml — Output assertions

The simplest possible suite. Four single-turn tests exercising every output assertion type.

| Test | Assertions | Expected |
|------|-----------|----------|
| responds to a simple greeting | `stop_reason`, `output_matches_regex` | Pass — model replies with a greeting and stops normally |
| includes user name in greeting | `output_contains` | Pass — output includes "Alice" |
| does not include unsolicited offers to help | `output_not_contains` | Pass — the skill instructs no follow-ups |
| greets in three languages | `output_matches_regex` ×2 | Pass — checks for "hola" and "こんにちは" |

**Features demonstrated:** `stop_reason`, `output_contains`, `output_not_contains`, `output_matches_regex`, `defaults` block.

---

### 02-llm-judge.eval.yaml — LLM judge assertions

Introduces `llm_judge` assertions with a dedicated `judge_model` and shows how to combine deterministic checks with qualitative judge criteria.

| Test | Assertions | Expected |
|------|-----------|----------|
| greeting is warm and friendly | `stop_reason`, `llm_judge` | Pass — judge confirms warm tone |
| personalized greeting feels natural | `output_contains`, `llm_judge` | **Fail** — `output_contains` passes (name present) but judge correctly critiques mechanical name appending across languages. The skill's template (`Hello Alice!` / `¡Hola Alice!` / `こんにちは Alice!`) doesn't adapt to each language's natural greeting conventions. This is a genuine quality finding. |
| follows three-language format | `llm_judge` | Pass — judge confirms three greetings in correct order |

**Features demonstrated:** `llm_judge` with `criteria`, `defaults.judge_model`, mixing deterministic + judge assertions.

---

### 03-tools-and-multi-turn.eval.yaml — Tools and multi-turn

The most assertion-dense suite. Demonstrates tool declarations, all tool assertion types, turn counting, scripted tool responses, and conversation history in single-turn tests.

| Test | Type | Assertions | Expected |
|------|------|-----------|----------|
| creates a file when asked | single_turn | `tool_called`, `tool_args_match` | Pass — model calls Write with matching file path |
| does not read for a simple write | single_turn | `tool_not_called` | Pass — no Read for a direct write |
| continues from prior tool context | single_turn | `tool_called` | Pass — model writes after seeing prior tool_calls/tool_result history |
| reads then writes a modified file | multi_turn | `tool_sequence`, `tool_called_times` ×2 | Pass — Read then Write, each exactly once |
| polls until ready then writes | multi_turn | `tool_called`, `tool_called_times`, `tool_called` | Pass — Read called 3+ times (response sequence: "pending", "pending", "ready") |
| completes single-step task in two turns | multi_turn | `tool_called`, `turn_count` | Pass — exactly 2 turns (tool call + confirmation) |
| completes read-modify-write within budget | multi_turn | `tool_sequence`, `turn_count` | Pass — Read→Write sequence in 1–3 turns |

**Features demonstrated:** `tools` (builtin), `tool_called`, `tool_not_called`, `tool_args_match`, `tool_sequence`, `tool_called_times` (exactly/min), `turn_count` (exactly/min/max), `tool_responses` (single response, response sequence, wildcard), conversation history with `tool_calls`/`tool_result` in single_turn, `max_turns`.

---

### 04-context.eval.yaml — Context file injection

Shows how to attach reference files as context at the suite and test level, including line ranges.

| Test | Assertions | Expected |
|------|-----------|----------|
| references suite-level context | `output_contains` | Pass — model sees `sample-ref.py` via suite context |
| uses test-level context with line range | `output_matches_regex` | Pass — model sees lines 5–7 of `sample-ref.py` |
| combines suite and test context | `output_matches_regex` ×2 | Pass — model sees both `sample-ref.py` (suite) and `SKILL.md` (test) |

**Features demonstrated:** Suite-level `context`, test-level `context`, `context.lines` ranges.

---

### 05-reliability.eval.yaml — Repeated runs and thresholds

Runs each test multiple times with `temperature: 0.7` to introduce variability, then checks pass rates against thresholds. Demonstrates baseline comparison.

| Test | Config | Assertions | Expected |
|------|--------|-----------|----------|
| greets with name reliably | 5 runs, 80% threshold, `baseline: true` | `output_contains` | Pass — "Alice" appears reliably across runs; baseline comparison included |
| always finishes without error | 10 runs, 100% threshold | `stop_reason` | Pass — model always stops normally |
| produces multilingual output | 5 runs, 80% threshold | `output_contains`, `output_matches_regex` | Pass — "Hola" and "こんにちは" present across runs |

**Features demonstrated:** `defaults.runs`, `defaults.pass_threshold`, `defaults.max_retries`, `defaults.concurrency`, per-test `runs`/`pass_threshold` overrides, `temperature` > 0, `baseline: true`.

---

### 06-conversation-prefix-inline.eval.yaml — Inline conversation prefix

Prepends a 3-exchange Python coding conversation before the test input. Uses `skill_position: top` (default) — the skill appears before the prefix, so the prefix dilutes the skill's influence.

| Test | Assertions | Expected |
|------|-----------|----------|
| skill activates after prior context | `stop_reason`, `output_contains` | Pass — model still greets "Bob" despite prior coding context |
| response quality survives context dilution | `stop_reason`, `llm_judge` | Pass — judge confirms three-language format without coding references |

**Features demonstrated:** `conversation_prefix.messages`, `skill_position: top`, `enable_caching: true`, `baseline: true` with prefix.

---

### 07-conversation-prefix-file.eval.yaml — External prefix file

Same conversation prefix as `06`, but loaded from `prefix-conversation.yaml` instead of inline. Uses `skill_position: bottom` — the prefix appears first, then the skill, placing the skill closer to the test input.

| Test | Assertions | Expected |
|------|-----------|----------|
| skill activates from bottom position | `stop_reason`, `output_contains` | Pass — model greets "Carol" with skill in bottom position |
| greets user by name from bottom position | `output_contains`, `stop_reason` | Pass — model includes "Eve" in greeting |

**Features demonstrated:** `conversation_prefix.file`, `skill_position: bottom`, `baseline: true`.

---

### 08-advanced.eval.yaml — System prompt, skill_only, custom tools

Combines three advanced features in one suite: a system prompt that establishes a persona, `skill_only` messages that are stripped from baseline runs, and a custom tool definition.

| Test | Type | Assertions | Expected |
|------|------|-----------|----------|
| system prompt establishes persona | single_turn | `llm_judge` | Pass — judge confirms enthusiastic, cheerful tone from system prompt |
| uses skill-only reference data | single_turn | `output_contains` | Pass — model uses reference data (skill_only messages present in skill run, stripped in baseline) |
| invokes custom lookup tool | multi_turn | `tool_called` | Pass — model calls the custom `greeting_lookup` tool |

**Features demonstrated:** `defaults.system_prompt`, `skill_only: true` on message pairs, custom tool with `name`/`description`/`input_schema`, `baseline: true`.

---

### Supporting files

| File | Purpose |
|------|---------|
| `prefix-conversation.yaml` | External conversation prefix (6 messages) referenced by `07` |
| `sample-skill/SKILL.md` | Toy greeting skill used by all numbered examples |
| `sample-ref.py` | Python file used as context in `04` |
| `code-review-skill.eval.yaml` | Real-world example with 9 tests against a code review skill |
| `code-review-skill/` | Skill definition and test fixtures for the code review suite |

## Feature coverage

Every functional feature of the framework is demonstrated by at least one example:

| Feature | Example |
|---------|---------|
| `stop_reason` | 01, 02, 06, 07 |
| `output_contains` | 01, 04, 05, 06, 07, 08 |
| `output_not_contains` | 01 |
| `output_matches_regex` | 01, 04, 05 |
| `tool_called` | 03, 08 |
| `tool_not_called` | 03 |
| `tool_called_times` (exactly/min) | 03 |
| `tool_args_match` | 03 |
| `tool_sequence` | 03 |
| `turn_count` (exactly/min/max) | 03 |
| `llm_judge` | 02, 06, 08 |
| `baseline: true` | 05, 06, 07, 08 |
| `skill_only: true` | 08 |
| `conversation_prefix.messages` | 06 |
| `conversation_prefix.file` | 07 |
| `skill_position: top` | 06 |
| `skill_position: bottom` | 07 |
| `enable_caching` | 06 |
| `system_prompt` | 08 |
| `judge_model` | 02, 08 |
| `runs` / `pass_threshold` | 05 |
| `concurrency` / `max_retries` | 05 |
| `context` (suite/test/lines) | 04 |
| Custom tool definition | 08 |
| Conversation history (tool_calls/tool_result) | 03 |
| `tool_responses` (single/sequence/wildcard) | 03 |
