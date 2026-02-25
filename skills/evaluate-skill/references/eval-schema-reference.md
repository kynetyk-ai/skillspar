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
  model: "claude-sonnet-4-5-20250929"
  judge_model: ""                      # Model for llm_judge assertions
  max_tokens: 4096
  temperature: 0
  runs: 1                              # Repeated runs per test (min: 1)
  pass_threshold: 1.0                  # Fraction of runs that must pass (0.0, 1.0]
  max_retries: 2                       # Retries on transient API errors
  concurrency: 1                       # Parallel test execution
```

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
