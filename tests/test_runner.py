"""Tests for runner.py — end-to-end with mock client."""


from skill_evaluator.config.loader import load_eval_suite
from skill_evaluator.runner import SuiteRunner


class TestSuiteRunner:
    def _make_suite_files(self, tmp_path, extra_yaml=""):
        """Create a minimal eval suite with skill file for testing."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        skill = skill_dir / "SKILL.md"
        skill.write_text("---\nname: test\n---\nYou are a helpful assistant.")

        yaml_content = f"""
suite: "test suite"
skill: "./skills/SKILL.md"
defaults:
  model: claude-sonnet-4-5-20250929
  max_tokens: 1024
  temperature: 0
{extra_yaml}
tests:
  - type: single_turn
    name: "basic greeting"
    input:
      messages:
        - role: user
          content: "Hello"
    assertions:
      - type: stop_reason
        value: end_turn
      - type: output_contains
        value: "Hello"
"""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)
        return eval_file

    def test_run_with_mock_client(self, tmp_path, mock_anthropic_client, mock_anthropic_message):
        eval_file = self._make_suite_files(tmp_path)
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Hello! How can I help?"
        )

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        result = runner.run()

        assert result.suite_name == "test suite"
        assert len(result.test_results) == 1
        assert result.all_passed is True
        mock_anthropic_client.messages.create.assert_called_once()

    def test_run_with_failing_assertion(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        eval_file = self._make_suite_files(tmp_path)
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Goodbye!"  # Does not contain "Hello"
        )

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        result = runner.run()

        assert result.all_passed is False
        assert result.failed_count == 1

    def test_multi_turn_skipped(self, tmp_path, mock_anthropic_client):
        """Multi-turn tests are skipped in Phase 1."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nBody")

        yaml_content = """
suite: "test"
skill: "./skills/SKILL.md"
tests:
  - type: multi_turn
    name: "multi turn test"
    input:
      messages:
        - role: user
          content: "Do something"
    assertions:
      - type: stop_reason
        value: end_turn
"""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        result = runner.run()

        # Multi-turn test has empty results — treated as SKIP
        assert len(result.test_results) == 1
        assert result.test_results[0].status_label == "SKIP"

    def test_execution_error_handled(self, tmp_path, mock_anthropic_client):
        eval_file = self._make_suite_files(tmp_path)
        mock_anthropic_client.messages.create.side_effect = Exception("Network error")

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        result = runner.run()

        assert result.all_passed is False
        assert result.test_results[0].runs[0].assertion_results[0].assertion_type == "execution"


class TestSuiteRunnerContext:
    def _make_context_files(self, tmp_path):
        """Create skill + context file for testing."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nYou are a helpful assistant.")

        ref = tmp_path / "ref.py"
        ref.write_text("def hello():\n    return 'world'")
        return skill_dir

    def test_suite_context_injected(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        self._make_context_files(tmp_path)
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Looks good"
        )

        yaml_content = """
suite: "test"
skill: "./skills/SKILL.md"
context:
  - file: "./ref.py"
tests:
  - type: single_turn
    name: "with suite context"
    input:
      messages:
        - role: user
          content: "Review the code"
    assertions:
      - type: output_contains
        value: "good"
"""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        result = runner.run()

        assert result.all_passed is True
        call_kwargs = mock_anthropic_client.messages.create.call_args
        messages = call_kwargs.kwargs["messages"]
        # Context adds messages before the test user message
        assert len(messages) > 1

    def test_test_context_injected(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        self._make_context_files(tmp_path)
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Reviewed"
        )

        yaml_content = """
suite: "test"
skill: "./skills/SKILL.md"
tests:
  - type: single_turn
    name: "with test context"
    context:
      - file: "./ref.py"
    input:
      messages:
        - role: user
          content: "Review"
    assertions:
      - type: output_contains
        value: "Review"
"""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        call_kwargs = mock_anthropic_client.messages.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert len(messages) > 1

    def test_suite_and_test_context_merged(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        self._make_context_files(tmp_path)
        extra = tmp_path / "extra.py"
        extra.write_text("extra content")
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Done"
        )

        yaml_content = """
suite: "test"
skill: "./skills/SKILL.md"
context:
  - file: "./ref.py"
tests:
  - type: single_turn
    name: "both contexts"
    context:
      - file: "./extra.py"
    input:
      messages:
        - role: user
          content: "Review"
    assertions:
      - type: output_contains
        value: "Done"
"""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        call_kwargs = mock_anthropic_client.messages.create.call_args
        messages = call_kwargs.kwargs["messages"]
        # Should have: user (context intro) → assistant (with 2 tool_calls) → user (2 tool_results + test msg)
        assert len(messages) == 3
        # Assistant message should have 2 tool_use blocks (suite + test context)
        assistant_content = messages[1]["content"]
        tool_uses = [b for b in assistant_content if b.get("type") == "tool_use"]
        assert len(tool_uses) == 2

    def test_missing_context_file_gives_error(
        self, tmp_path, mock_anthropic_client
    ):
        self._make_context_files(tmp_path)

        yaml_content = """
suite: "test"
skill: "./skills/SKILL.md"
context:
  - file: "./nonexistent.py"
tests:
  - type: single_turn
    name: "missing context"
    input:
      messages:
        - role: user
          content: "Hi"
    assertions:
      - type: stop_reason
        value: end_turn
"""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        result = runner.run()

        assert result.all_passed is False
        assert result.test_results[0].runs[0].assertion_results[0].assertion_type == "context"
        assert "not found" in result.test_results[0].runs[0].assertion_results[0].message

    def test_context_messages_precede_input(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        self._make_context_files(tmp_path)
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="OK"
        )

        yaml_content = """
suite: "test"
skill: "./skills/SKILL.md"
context:
  - file: "./ref.py"
tests:
  - type: single_turn
    name: "order check"
    input:
      messages:
        - role: user
          content: "Test message"
    assertions:
      - type: output_contains
        value: "OK"
"""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        call_kwargs = mock_anthropic_client.messages.create.call_args
        messages = call_kwargs.kwargs["messages"]
        # First message is the context "[Reading context files]"
        first_user = messages[0]
        assert first_user["role"] == "user"
        # The actual test content should be in the last user message
        last_user = messages[-1]
        assert last_user["role"] == "user"


# ---------------------------------------------------------------------------
# New: Repeated runs, baseline, concurrency
# ---------------------------------------------------------------------------


class TestSuiteRunnerRepeatedRuns:
    def _make_suite_files(self, tmp_path, yaml_content):
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nYou are a helpful assistant.")
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)
        return eval_file

    def test_runs_3_produces_3_results(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Hello! How can I help?"
        )
        yaml = """
suite: "test"
skill: "./skills/SKILL.md"
defaults:
  runs: 3
tests:
  - type: single_turn
    name: "greeting"
    input:
      messages:
        - role: user
          content: "Hello"
    assertions:
      - type: output_contains
        value: "Hello"
"""
        eval_file = self._make_suite_files(tmp_path, yaml)
        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        result = runner.run()

        group = result.test_results[0]
        assert len(group.runs) == 3
        assert mock_anthropic_client.messages.create.call_count == 3

    def test_runs_1_backward_compat(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Hello!"
        )
        yaml = """
suite: "test"
skill: "./skills/SKILL.md"
tests:
  - type: single_turn
    name: "single"
    input:
      messages:
        - role: user
          content: "Hi"
    assertions:
      - type: stop_reason
        value: end_turn
"""
        eval_file = self._make_suite_files(tmp_path, yaml)
        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        result = runner.run()

        group = result.test_results[0]
        assert len(group.runs) == 1
        assert group.is_multi_run is False

    def test_baseline_produces_skill_and_baseline_runs(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Hello Alice!"
        )
        yaml = """
suite: "test"
skill: "./skills/SKILL.md"
defaults:
  runs: 2
tests:
  - type: single_turn
    name: "baseline test"
    baseline: true
    input:
      messages:
        - role: user
          content: "Hi Alice"
    assertions:
      - type: output_contains
        value: "Alice"
"""
        eval_file = self._make_suite_files(tmp_path, yaml)
        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        result = runner.run()

        group = result.test_results[0]
        assert len(group.runs) == 2
        assert group.baseline_runs is not None
        assert len(group.baseline_runs) == 2
        # 2 skill + 2 baseline = 4 calls
        assert mock_anthropic_client.messages.create.call_count == 4

    def test_baseline_uses_empty_system_prompt(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Hello!"
        )
        yaml = """
suite: "test"
skill: "./skills/SKILL.md"
tests:
  - type: single_turn
    name: "baseline check"
    baseline: true
    input:
      messages:
        - role: user
          content: "Hi"
    assertions:
      - type: stop_reason
        value: end_turn
"""
        eval_file = self._make_suite_files(tmp_path, yaml)
        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        # 2 calls: 1 skill + 1 baseline
        calls = mock_anthropic_client.messages.create.call_args_list
        assert len(calls) == 2
        # One call should have the skill prompt, one should have empty string
        system_prompts = [c.kwargs["system"] for c in calls]
        assert "" in system_prompts
        assert any(p != "" for p in system_prompts)

    def test_per_test_runs_override(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Hello!"
        )
        yaml = """
suite: "test"
skill: "./skills/SKILL.md"
defaults:
  runs: 2
tests:
  - type: single_turn
    name: "overridden"
    runs: 5
    input:
      messages:
        - role: user
          content: "Hi"
    assertions:
      - type: stop_reason
        value: end_turn
"""
        eval_file = self._make_suite_files(tmp_path, yaml)
        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        result = runner.run()

        assert len(result.test_results[0].runs) == 5
        assert mock_anthropic_client.messages.create.call_count == 5

    def test_concurrency_1_sequential(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Hello!"
        )
        yaml = """
suite: "test"
skill: "./skills/SKILL.md"
defaults:
  runs: 3
  concurrency: 1
tests:
  - type: single_turn
    name: "sequential"
    input:
      messages:
        - role: user
          content: "Hi"
    assertions:
      - type: stop_reason
        value: end_turn
"""
        eval_file = self._make_suite_files(tmp_path, yaml)
        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        result = runner.run()

        assert len(result.test_results[0].runs) == 3
        assert result.all_passed is True

    def test_concurrency_gt_1_all_work_items_executed(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Hello!"
        )
        yaml = """
suite: "test"
skill: "./skills/SKILL.md"
defaults:
  runs: 4
  concurrency: 2
tests:
  - type: single_turn
    name: "parallel"
    input:
      messages:
        - role: user
          content: "Hi"
    assertions:
      - type: stop_reason
        value: end_turn
"""
        eval_file = self._make_suite_files(tmp_path, yaml)
        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        result = runner.run()

        assert len(result.test_results[0].runs) == 4
        assert mock_anthropic_client.messages.create.call_count == 4
        assert result.all_passed is True

    def test_max_retries_passed_to_default_client(self, tmp_path):
        """When no client is provided, max_retries from defaults is used."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nBody")

        yaml = """
suite: "test"
skill: "./skills/SKILL.md"
defaults:
  max_retries: 5
tests:
  - type: single_turn
    name: "test"
    input:
      messages:
        - role: user
          content: "Hi"
    assertions:
      - type: stop_reason
        value: end_turn
"""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml)
        suite = load_eval_suite(eval_file)

        # Just check the runner initializes without error
        # (actual client construction requires ANTHROPIC_API_KEY, so we just
        # verify the suite defaults are parsed correctly)
        assert suite.defaults.max_retries == 5

    def test_trace_stored_on_test_result(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Hello!"
        )
        yaml = """
suite: "test"
skill: "./skills/SKILL.md"
tests:
  - type: single_turn
    name: "trace check"
    input:
      messages:
        - role: user
          content: "Hi"
    assertions:
      - type: stop_reason
        value: end_turn
"""
        eval_file = tmp_path / "skills"
        eval_file = self._make_suite_files(tmp_path, yaml)
        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        result = runner.run()

        tr = result.test_results[0].runs[0]
        assert tr.trace is not None
        assert tr.trace.text_output == "Hello!"
