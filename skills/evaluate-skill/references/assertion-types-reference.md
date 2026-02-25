# Assertion Types Reference

## Output Content (Deterministic)

```yaml
- type: stop_reason
  value: "end_turn"                    # or "tool_use", "max_tokens"

- type: output_contains
  value: "exact substring"            # Case-sensitive substring match

- type: output_not_contains
  value: "forbidden substring"        # Fails if substring found

- type: output_matches_regex
  pattern: "^## Summary\\n"           # Python regex on full text output
```

## Tool Usage (Deterministic)

```yaml
- type: tool_called
  tool: Read                           # At least one call to this tool

- type: tool_not_called
  tool: Bash                           # Zero calls to this tool

- type: tool_called_times
  tool: Read
  exactly: 1                          # Or use min/max instead of exactly
  # min: 1
  # max: 3

- type: tool_args_match
  tool: Write
  path: "$.file_path"                 # JSONPath into tool input
  pattern: "\\.py$"                   # Regex on extracted value

- type: tool_sequence
  tools: [Read, Edit]                 # Must appear in this order (subsequence)
```

## Conversation Shape (Deterministic)

```yaml
- type: turn_count
  exactly: 3                          # Or use min/max
  # min: 2
  # max: 5
```

## LLM Judge (Subjective)

```yaml
- type: llm_judge
  criteria: |
    Evaluate whether the response meets this quality bar:
    - Is the tone constructive and professional?
    - Are suggestions actionable?
  model: ""                           # Optional, overrides defaults.judge_model
```
