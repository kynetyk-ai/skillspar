# CLI Reference

## Running Suites

```
skillspar run [OPTIONS] EVAL_FILES...
```

`EVAL_FILES` accepts file paths, directories (recursive), and globs. Multiple suites run sequentially; a failure in one does not abort others.

### Flags

| Flag | Description |
|------|-------------|
| `--runs N` | Override runs per test |
| `--concurrency N` | Max parallel API calls |
| `--output PATH` | Write JSON report to file |
| `--format json\|junit` | Report format (default: inferred from extension, or json) |
| `--filter PATTERN` | Only run tests whose name contains this substring |
| `--model MODEL` | Override the suite default model |
| `--verbose` | Show per-assertion details in console output |
| `--log-level LEVEL` | Logging verbosity: DEBUG, INFO, WARNING, ERROR |

### Examples

```bash
# Single suite with JSON output
skillspar run suite.eval.yaml --output results.json

# Multiple runs for reliability testing
skillspar run suite.eval.yaml --runs 5 --concurrency 4 --output results.json

# All suites in a directory
skillspar run examples/

# Filter to specific tests
skillspar run suite.eval.yaml --filter "greeting" --verbose
```

## Snapshots

Save and compare results over time:

```bash
# Save a snapshot after running
skillspar snapshot save suite.eval.yaml

# List saved snapshots
skillspar snapshot list
skillspar snapshot list --suite "greeting skill"

# Diff two snapshots
skillspar snapshot diff before.json after.json

# Run, diff against latest snapshot, and save
skillspar snapshot diff --latest suite.eval.yaml
```

## Watch Mode

Re-runs automatically when eval file, skill file, or context files change:

```bash
skillspar watch suite.eval.yaml
skillspar watch suite.eval.yaml --filter "greeting" --verbose --debounce 500
```

Supports the same flags as `run`, plus `--debounce` (ms, default: 300).

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tests passed |
| 1 | One or more tests failed |
| 2 | Configuration or validation error (bad YAML, missing skill file, no matching tests) |

In multi-suite runs, exit code 2 takes priority over 1.

## Environment

- `ANTHROPIC_API_KEY` — required. Set in environment or a `.env` file in the working directory.
- Reports are written to the path specified by `--output`. Without `--output`, results are only printed to console.
