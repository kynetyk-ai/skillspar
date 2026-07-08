# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **OpenAI-compatible provider support**: `provider: openai` in suite defaults (or
  `--provider openai`) runs suites against any endpoint speaking the OpenAI Chat
  Completions API — OpenAI, OpenRouter, LiteLLM, Ollama, vLLM — with `base_url`,
  `api_key_env`, and `judge_provider` configuration. Install via
  `pip install "skillspar[openai]"`.
- Cross-provider LLM judging: pin the judge to a fixed provider/model while the
  model-under-test runs elsewhere (`judge_provider` + `judge_model`).
- `stop_reason` assertions accept OpenAI vocabulary (`stop`, `tool_calls`, `length`)
  as aliases for the canonical values.
- Pricing entries support `cache_semantics: openai` in `SKILLSPAR_PRICING_FILE`.
- New env vars: `OPENAI_API_KEY`, `SKILLSPAR_PROVIDER`, `SKILLSPAR_BASE_URL`,
  `SKILLSPAR_JUDGE_PROVIDER`.
- JSON reports record `provider`, `base_url`, and `judge_provider` for reproducibility.

### Changed

- Internal provider abstraction (`skill_evaluator.providers`): executors and the LLM
  judge now consume a `Provider` protocol instead of the Anthropic SDK directly.
- Prompt caching (cache_control breakpoints, cache cost reporting, prefix token
  threshold warning) is now explicitly Anthropic-only.
- API-key pre-flight checks are provider-aware and run per-suite after config
  resolution (also covering `snapshot save`/`diff`).

## [0.1.0] - 2026-07-08

Initial release.

### Added

- **Test execution**: single-turn and multi-turn (agentic loop) test types with
  scripted mock tool responses, repeated runs with `pass_threshold`, and
  concurrent execution.
- **Baseline comparison**: `baseline: true` runs each test with and without the
  skill to measure the skill's marginal behavioral impact ("steer"), with
  `skill_only` message exclusion.
- **Assertions**: `tool_called`, `tool_not_called`, `tool_sequence`,
  `tool_called_times`, `tool_args_match`, `turn_count`, `output_contains`,
  `output_not_contains`, `output_matches_regex`, `stop_reason`, and `llm_judge`
  (LLM-scored subjective criteria with configurable judge model).
- **Mid-conversation testing**: `conversation_prefix` prepends simulated prior
  conversation with `skill_position` control and prompt-caching breakpoints.
- **Context injection**: suite-level and per-test context files with line ranges,
  modeled as simulated tool results.
- **Reporting**: Rich console output, structured JSON reports (cost, duration,
  cache summary), JUnit XML for CI, CI-friendly exit codes.
- **Snapshots**: `skillspar snapshot save|list|diff` for temporal diffing and
  steer-erosion detection.
- **Watch mode**: `skillspar watch` re-runs suites on file changes with
  iteration-over-iteration diffs.
- **Multi-suite execution**: directories/globs with an aggregated dashboard.
- **Claude Code plugin**: `/skillspar:evaluate` meta-skill that analyzes a
  SKILL.md and generates a starter eval suite.

[Unreleased]: https://github.com/kynetyk-ai/skillspar/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/kynetyk-ai/skillspar/releases/tag/v0.1.0
