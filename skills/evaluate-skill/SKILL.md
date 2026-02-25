---
name: evaluate-skill
description: Analyze a SKILL.md and generate a .eval.yaml test suite with baseline comparison measuring the skill's marginal behavioral impact
---

# Skill Evaluation

This skill produces `.eval.yaml` test suites for the Skillspar framework. Given a target SKILL.md, the task is to extract testable behavioral claims and generate tests that measure the skill's **steer** — its marginal behavioral impact over the base model.

## A: Analysis Protocol

1. **Read the target SKILL.md** using the Read tool. Parse its frontmatter (`name`, `description`) and body.
2. **Extract behavioral claims** from the body. A claim is any statement about what the skill should or should not do. Classify each as:
   - **Deterministic** — verifiable by string, regex, or tool-use checks (output format, required keywords, tool-use patterns, workflow sequences, forbidden behaviors)
   - **Subjective** — requires judgment about quality, tone, or completeness
3. **Enter plan mode.** Present the user with:
   - The extracted claims, grouped by category
   - A proposed assertion type for each claim (use the decision table in section B)
   - A recommended test structure (single-turn vs multi-turn for each)
   - Do NOT write any files until the user approves the plan.
4. **Offer a coverage strategy.** Ask the user:
   - **Comprehensive**: one test per claim, full coverage
   - **Focused**: collaborate to identify the 5–8 most critical behavioral assertions — the claims that represent the skill's core steer vs. nice-to-haves. Recommend which claims are highest-value and let the user decide what to keep.
5. **Generate the `.eval.yaml`** after approval, following the schema in `references/eval-schema-reference.md`.

## B: Assertion Selection

Use this table to pick the right assertion type for each claim:

| Claim type | Assertion | Example |
|---|---|---|
| Must contain a literal keyword/phrase | `output_contains` | "Always include a Summary section" |
| Must NOT contain something | `output_not_contains` | "Never include apologies" |
| Format matchable by regex | `output_matches_regex` | "Use ## headings for each section" |
| Must use a specific tool | `tool_called` | "Always read the file first" |
| Must NOT use a specific tool | `tool_not_called` | "Never execute shell commands" |
| Tool used N times | `tool_called_times` | "Read each file exactly once" |
| Tools in specific order | `tool_sequence` | "Read before Edit" |
| Tool argument follows pattern | `tool_args_match` | "Only edit .py files" |
| Multi-step conversation length | `turn_count` | "Complete in 3 or fewer turns" |
| Subjective quality | `llm_judge` | "Be constructive", "Be thorough" |

Subjective claims (tone, helpfulness, thoroughness) must use `llm_judge`. Never approximate them with `output_contains` or `output_matches_regex`.

## C: Test Design Rules

- Set `baseline: true` on every test. Disable only when testing behavior the base model never exhibits; add a comment explaining why.
- Default to `single_turn`. Use `multi_turn` only when the claim requires sequential tool calls with intermediate results.
- Provide reference material as `tool_result` messages in conversation history, not as user-message context. Models weight information differently by source.
- Consider adding a `conversation_prefix` when the skill is likely to be used mid-conversation (most skills are). A prefix simulates prior context to test whether the skill's steer persists after context dilution. This is optional — only suggest it if the skill's use case implies mid-session activation.

## D: Conventions

1. **Verb-first test names**: `"produces structured output with severity labels"`, not `"test_1"`.
2. **One test per claim** so failures are diagnostic.
3. **At least one holistic `llm_judge` test** evaluating overall response quality against the skill's purpose.
4. **Realistic, varied user messages** — don't reuse the same input across tests.
5. **Progressive discovery via tool results** — model reference material (code, research, skill package docs) as `tool_result` messages rather than inline user context. A Read result is the simplest form; this lets the model encounter information the way it would in real usage.

## E: Output

1. **Write the `.eval.yaml`** using the Write tool, placed alongside or near the target SKILL.md.
2. **Write any context files** referenced by the suite.
3. **Validate the suite** by running:
   ```bash
   python skills/evaluate-skill/scripts/validate_eval.py <path-to-your-eval.yaml>
   ```
   This checks both schema correctness and common semantic mistakes (mismatched tool_result ids, undeclared tools in assertions, multi_turn without tool_responses, etc.). If validation fails, fix the reported errors and re-run until it passes. The error messages explain exactly what's wrong and how to fix it.
4. **Summarize**: total test count, claims covered with their tests, any untestable claims with explanation, and assertion type distribution.

## References

Before writing the `.eval.yaml`, read these reference files for the full schema and assertion syntax:
- `references/eval-schema-reference.md` — complete `.eval.yaml` structure, fields, and defaults
- `references/assertion-types-reference.md` — detailed syntax for every assertion type
