# JSON Output Schema Reference

Skillspar produces JSON reports via `--output results.json`. This reference documents the structure of single-suite and multi-suite reports.

## Single-Suite Report

```json
{
  "schema_version": "1",                    // Fixed version string
  "suite": "suite name",                    // Suite name from .eval.yaml
  "skill": "./path/to/SKILL.md",           // Skill path from .eval.yaml
  "defaults": {                             // Resolved defaults (see below)
    "model": "claude-sonnet-4-5-20250929",
    "max_tokens": 4096,
    "temperature": 0,
    "runs": 1,
    "pass_threshold": 1.0,
    "max_retries": 2,
    "concurrency": 1,
    "judge_model": "",                      // Present if set
    "system_prompt": ""                     // Present if set
  },
  "timestamp": "2025-02-26T12:00:00Z",     // UTC ISO timestamp
  "run_id": "uuid",                         // Optional, run identifier
  "skill_file_hash": "sha256...",           // Optional, hash of skill file
  "tests": [],                              // Array of test results (see below)
  "summary": {}                             // Aggregated metrics (see below)
}
```

## Test Result

Each entry in the `tests` array:

```json
{
  "name": "responds with greeting",         // Test name from .eval.yaml
  "config": {
    "runs": 1,                              // Runs configured for this test
    "pass_threshold": 1.0,                  // Pass threshold for this test
    "baseline": false                       // Whether baseline was enabled
  },
  "summary": {
    "pass_count": 1,                        // Skill runs that passed
    "total_runs": 1,                        // Total skill runs executed
    "pass_rate": 1.0,                       // pass_count / total_runs
    "passed": true,                         // Overall pass/fail (pass_rate >= threshold)
    "duration_seconds": 2.345               // Optional, total duration (3 decimals)
  },
  "runs": [],                               // Array of individual run results
  "baseline_runs": [],                       // Present only when baseline: true
  "baseline_summary": {                      // Present only when baseline: true
    "pass_count": 0,
    "total_runs": 1,
    "pass_rate": 0.0
  }
}
```

## Run Result

Each entry in `runs` or `baseline_runs`:

```json
{
  "run_index": 0,                           // 0-based index in run sequence
  "passed": true,                           // All assertions passed for this run
  "assertions": [],                         // Array of assertion results (see below)
  "duration_seconds": 1.234,                // Optional, execution time (3 decimals)
  "cost_usd": 0.001234,                     // Optional, cost for this run (6 decimals)
  "trace": {                                // Optional, execution trace (see below)
    "turns": []
  }
}
```

## Assertion Result

Each entry in `assertions`:

```json
{
  "type": "output_contains",                // Assertion type
  "status": "passed",                       // "passed" | "failed" | "skipped" | "error"
  "message": "Output contains 'hello'",     // Human-readable description
  "details": {}                             // Optional, assertion-specific details
}
```

## Trace

The `trace` object contains the full conversation turns:

```json
{
  "trace": {
    "turns": [
      {
        "text_output": "The assistant said...",   // Text portion of response
        "tool_calls": [                            // Tool calls made in this turn
          {
            "id": "tooluse_123",
            "name": "Read",
            "input": { "file_path": "/some/file" }
          }
        ],
        "stop_reason": "end_turn",                 // "end_turn" | "tool_use" | "max_tokens"
        "usage": {
          "input_tokens": 150,
          "output_tokens": 50,
          "cache_creation_input_tokens": 0,        // Optional
          "cache_read_input_tokens": 0             // Optional
        }
      }
    ]
  }
}
```

## Summary (Top-Level)

```json
{
  "summary": {
    "total_tests": 5,
    "passed_tests": 4,
    "failed_tests": 1,
    "all_passed": false,
    "total_api_calls": 12,                  // Sum of turn counts across all runs
    "total_tokens": {
      "input_tokens": 1500,
      "output_tokens": 750
    },
    "total_duration_seconds": 5.678,        // Optional (3 decimals)
    "cache_summary": {                      // Present only if caching occurred
      "cache_creation_input_tokens": 1000,
      "cache_read_input_tokens": 500,
      "estimated_savings_usd": 0.000500     // Optional (6 decimals)
    },
    "cost": {                               // Present only if cost data available
      "total_cost_usd": 0.025000,           // Skill + baseline (6 decimals)
      "skill_cost_usd": 0.020000,           // Skill runs only
      "baseline_cost_usd": 0.005000         // Optional, present if baseline runs exist
    }
  }
}
```

## Multi-Suite Report

When multiple eval files are run, the report wraps individual suite reports:

```json
{
  "schema_version": "1",
  "type": "multi_suite",                    // Discriminator field
  "timestamp": "2025-02-26T12:00:00Z",
  "suites": [                               // Array of suite results
    {
      "eval_file": "/path/to/suite.eval.yaml"
      // ... full single-suite report fields (schema_version, suite, skill, etc.)
    },
    {
      "eval_file": "/path/to/broken.eval.yaml",
      "suite": "broken suite",              // Suite name if available
      "error": "Config validation failed: ..."  // Error message (no test data)
    }
  ],
  "summary": {
    "total_suites": 3,
    "passed_suites": 2,
    "failed_suites": 0,                     // Suites with test failures
    "error_suites": 1,                      // Suites with config/execution errors
    "all_passed": false,
    "total_cost_usd": 0.150000              // Optional, sum of all suite costs
  }
}
```

Each entry in `suites` is either a full single-suite report (with an added `eval_file` field) or a minimal error object with `eval_file`, `suite`, and `error`.
