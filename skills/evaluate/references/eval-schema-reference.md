# .eval.yaml Schema Reference

## Top-Level Fields

```yaml
suite: "descriptive suite name"        # Required
skill: "./relative/path/to/SKILL.md"   # Required, relative to this .eval.yaml
context:                               # Optional, suite-level context files
  - file: "./path/to/file.ext"
    lines: [1, 50]                     # Optional [start, end] line range
```

## Defaults

All fields are optional and have sensible defaults:

```yaml
defaults:
  system_prompt: ""                    # Baseline agent persona (constant across skill/baseline runs)
  model: "claude-sonnet-4-5-20250929"
  judge_model: ""                      # Model for llm_judge assertions
  max_tokens: 4096
  temperature: 0
  runs: 1                              # Repeated runs per test (min: 1)
  pass_threshold: 1.0                  # Fraction of runs that must pass (0.0, 1.0]
  max_retries: 2                       # Retries on transient API errors
  concurrency: 1                       # Parallel test execution
  enable_caching: true                 # Prompt caching for prefix/system prompt
```

The `system_prompt` is sent as the API system message on every run (both skill and baseline). Use it to establish a persona or behavioral constraints that the skill builds on top of, rather than for content that should only appear in skill runs.

## Conversation Prefix

Prepend a simulated conversation to test whether a skill still steers behavior after context dilution. The prefix appears between the skill prompt and test input in every run (including baseline).

Inline messages:

```yaml
conversation_prefix:
  skill_position: top                  # Optional: "top" (default) or "bottom"
  messages:
    - role: user
      content: "Can you help me refactor this function?"
    - role: assistant
      content: "Sure! Could you share the function?"
    - role: user
      content: "Here it is: def foo(): pass"
    - role: assistant
      content: "Here's the refactored version: ..."
```

Or reference an external YAML file:

```yaml
conversation_prefix:
  file: "./prefix-conversation.yaml"   # Relative to the .eval.yaml
```

Rules:
- Specify either `messages` or `file`, not both
- Messages must end with an `assistant` message
- When `enable_caching: true` (default), the last prefix message gets a cache breakpoint so the prefix is shared across all tests in each skill/baseline group
- `skill_position` controls where the skill sits relative to the prefix (see Message Ordering below)

## Tools Declaration

```yaml
tools:                                 # Optional
  - builtin: Read                      # Built-ins: Read, Write, Edit, Bash, Glob, Grep
  - builtin: Write
  - name: "custom_tool"               # Or define custom tools
    description: "Does something"
    input_schema:
      type: object
      properties:
        arg1: { type: string }
      required: [arg1]
```

## Single-Turn Test

```yaml
tests:
  - name: "descriptive verb-first name"
    type: single_turn
    baseline: true
    context:                           # Optional, test-level context
      - file: "./context-file.py"
    input:
      messages:
        - role: user
          content: "The user message"
    assertions:
      - type: output_contains
        value: "expected substring"
```

## Single-Turn with Conversation History

Use this to simulate prior tool interactions without running a full multi-turn loop:

```yaml
  - name: "handles follow-up correctly"
    type: single_turn
    baseline: true
    input:
      messages:
        - role: user
          content: "First message"
        - role: assistant
          content: "First response"
          tool_calls:
            - id: "tc_001"
              name: Read
              input: { file_path: "/some/file.py" }
        - role: tool_result
          tool_use_id: "tc_001"
          content: "file contents here"
        - role: user
          content: "Follow-up message"
    assertions:
      - type: llm_judge
        criteria: "Response correctly builds on prior context"
```

## Skill-Only Messages

Mark messages as `skill_only: true` to include them only in skill runs, stripping them from baseline runs. This is useful when test messages simulate the model reading skill reference material — baseline should test the model without that domain knowledge.

```yaml
  - name: "uses reference data correctly"
    type: single_turn
    baseline: true
    input:
      messages:
        - role: user
          content: "Show me the JSON."
        - role: assistant
          skill_only: true           # stripped for baseline
          content: "Let me check the reference."
          tool_calls:
            - id: "tc_001"
              name: Read
              input: { file_path: "references/schema.md" }
        - role: tool_result
          skill_only: true           # stripped for baseline
          tool_use_id: "tc_001"
          content: "## Schema reference data ..."
        - role: user
          content: "Build it."
    assertions:
      - type: output_contains
        value: "expected output"
```

Rules:
- Default is `false` — messages are included in both skill and baseline runs
- Always mark both the `assistant` (with tool_calls) and its matching `tool_result` messages as `skill_only: true` together — orphaning one side produces an invalid conversation for baseline
- `skill_only` has no effect on tests without `baseline: true`

## Multi-Turn Test

```yaml
  - name: "completes multi-step workflow"
    type: multi_turn
    baseline: true
    max_turns: 10                      # Max API round-trips
    input:
      messages:
        - role: user
          content: "Do the multi-step thing"
    tool_responses:                    # Scripted responses for tool calls
      - match:
          tool: Read
        response:
          content: "file contents"
      - match:
          tool: Write
        response:
          content: "File written successfully"
      - match: "*"                     # Wildcard catch-all
        response:
          content: "OK"
    assertions:
      - type: tool_sequence
        tools: [Read, Write]
```

## Message Ordering

The `skill_position` field on `conversation_prefix` controls ordering:

**`top` (default):** Skill → Prefix → Context → Test

1. **Skill message** (user) — injected from the SKILL.md
2. **Prefix messages** (user/assistant pairs) — from `conversation_prefix`
3. **Context messages** (user/assistant/tool_result) — from suite-level or test-level `context`
4. **Test input messages** (user) — from `test.input.messages`

**`bottom`:** Prefix → Skill → Context → Test

1. **Prefix messages** (user/assistant pairs) — from `conversation_prefix`
2. **Skill message** (user) — injected from the SKILL.md
3. **Context messages** (user/assistant/tool_result) — from suite-level or test-level `context`
4. **Test input messages** (user) — from `test.input.messages`

Use `top` (default) to test whether the skill survives context dilution — the prefix pushes the skill further from the test input. Use `bottom` to place the skill closer to the test input, simulating a skill activated mid-conversation.

Consecutive same-role messages are automatically coalesced to maintain valid role alternation.
