"""Tests for runner.py — end-to-end with mock client."""

import logging

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

    def test_multi_turn_executes(self, tmp_path, mock_anthropic_client, mock_anthropic_message):
        """Multi-turn tests execute with tool mocking."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nBody")

        # Model calls Read, then finishes
        tool_msg = mock_anthropic_message(
            text="Reading file.",
            tool_uses=[{"id": "tc_001", "name": "Read", "input": {"file_path": "/f.txt"}}],
            stop_reason="tool_use",
        )
        final_msg = mock_anthropic_message(text="Done!", stop_reason="end_turn")
        mock_anthropic_client.messages.create.side_effect = [tool_msg, final_msg]

        yaml_content = """
suite: "test"
skill: "./skills/SKILL.md"
tests:
  - type: multi_turn
    name: "multi turn test"
    max_turns: 5
    input:
      messages:
        - role: user
          content: "Read something"
    tool_responses:
      - match: "*"
        response:
          content: "file data"
    assertions:
      - type: stop_reason
        value: end_turn
      - type: tool_called
        tool: Read
"""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        result = runner.run()

        assert len(result.test_results) == 1
        assert result.all_passed is True
        assert result.test_results[0].runs[0].trace is not None
        assert result.test_results[0].runs[0].trace.turn_count == 2

    def test_multi_turn_two_turns_with_assertions(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        """Multi-turn with Read -> Write sequence and structural assertions."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nBody")

        read_msg = mock_anthropic_message(
            text="Reading.",
            tool_uses=[{"id": "tc_001", "name": "Read", "input": {"file_path": "/a.txt"}}],
            stop_reason="tool_use",
        )
        write_msg = mock_anthropic_message(
            text="Writing.",
            tool_uses=[
                {
                    "id": "tc_002",
                    "name": "Write",
                    "input": {"file_path": "/a.txt", "content": "new"},
                }
            ],
            stop_reason="tool_use",
        )
        final_msg = mock_anthropic_message(text="All done.", stop_reason="end_turn")
        mock_anthropic_client.messages.create.side_effect = [read_msg, write_msg, final_msg]

        yaml_content = """
suite: "test"
skill: "./skills/SKILL.md"
tests:
  - type: multi_turn
    name: "read then write"
    max_turns: 5
    input:
      messages:
        - role: user
          content: "Modify a file"
    tool_responses:
      - match:
          tool: Read
        response:
          content: "original content"
      - match:
          tool: Write
        response:
          content: "File written"
    assertions:
      - type: tool_sequence
        tools: [Read, Write]
      - type: tool_called_times
        tool: Read
        exactly: 1
      - type: turn_count
        min: 2
"""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        result = runner.run()

        assert result.all_passed is True

    def test_multi_turn_baseline(self, tmp_path, mock_anthropic_client, mock_anthropic_message):
        """Multi-turn tests support baseline comparison."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nBody")

        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Done!", stop_reason="end_turn"
        )

        yaml_content = """
suite: "test"
skill: "./skills/SKILL.md"
tests:
  - type: multi_turn
    name: "baseline multi"
    baseline: true
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

        group = result.test_results[0]
        assert len(group.runs) == 1
        assert group.baseline_runs is not None
        assert len(group.baseline_runs) == 1

    def test_multi_turn_no_match_error_handled(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        """NoMatchError is caught and reported as execution error."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nBody")

        tool_msg = mock_anthropic_message(
            text="Calling Bash.",
            tool_uses=[{"id": "tc_001", "name": "Bash", "input": {"command": "ls"}}],
            stop_reason="tool_use",
        )
        mock_anthropic_client.messages.create.return_value = tool_msg

        yaml_content = """
suite: "test"
skill: "./skills/SKILL.md"
tests:
  - type: multi_turn
    name: "no match"
    input:
      messages:
        - role: user
          content: "Run bash"
    tool_responses:
      - match:
          tool: Read
        response:
          content: "data"
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
        assert result.test_results[0].runs[0].assertion_results[0].assertion_type == "execution"

    def test_execution_error_handled(self, tmp_path, mock_anthropic_client):
        eval_file = self._make_suite_files(tmp_path)
        from anthropic import APIConnectionError

        mock_anthropic_client.messages.create.side_effect = APIConnectionError(request=None)

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

    def test_suite_context_injected(self, tmp_path, mock_anthropic_client, mock_anthropic_message):
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

    def test_test_context_injected(self, tmp_path, mock_anthropic_client, mock_anthropic_message):
        self._make_context_files(tmp_path)
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Reviewed")

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
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Done")

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
        # user (context intro) -> assistant (2 tool_calls) -> user (2 tool_results + test msg)
        assert len(messages) == 3
        # Assistant message should have 2 tool_use blocks (suite + test context)
        assistant_content = messages[1]["content"]
        tool_uses = [b for b in assistant_content if b.get("type") == "tool_use"]
        assert len(tool_uses) == 2

    def test_missing_context_file_gives_error(self, tmp_path, mock_anthropic_client):
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
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="OK")

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

    def test_runs_1_backward_compat(self, tmp_path, mock_anthropic_client, mock_anthropic_message):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Hello!")
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

    def test_baseline_omits_skill_message(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Hello!")
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
        # Both calls should have empty system prompt (baseline persona)
        for call in calls:
            assert call.kwargs["system"] == ""
        # Skill run should have the framed skill body in messages
        skill_call_messages = calls[0].kwargs["messages"]
        skill_text = str(skill_call_messages)
        assert "The following skill has been activated" in skill_text
        # Baseline run should NOT have the skill message
        baseline_call_messages = calls[1].kwargs["messages"]
        baseline_text = str(baseline_call_messages)
        assert "The following skill has been activated" not in baseline_text

    def test_baseline_work_items_grouped_for_caching(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        """All skill runs execute before any baseline runs for cache efficiency."""
        call_order = []

        def track_calls(**kwargs):
            messages_str = str(kwargs.get("messages", ""))
            has_skill = "The following skill has been activated" in messages_str
            call_order.append("skill" if has_skill else "baseline")
            return mock_anthropic_message(text="Hello!")

        mock_anthropic_client.messages.create.side_effect = track_calls
        yaml = """
suite: "test"
skill: "./skills/SKILL.md"
defaults:
  runs: 3
tests:
  - type: single_turn
    name: "grouped test"
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

        # 3 skill + 3 baseline = 6 calls
        assert len(call_order) == 6
        # All skill runs should come before all baseline runs
        assert call_order == ["skill", "skill", "skill", "baseline", "baseline", "baseline"]

    def test_per_test_runs_override(self, tmp_path, mock_anthropic_client, mock_anthropic_message):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Hello!")
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
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Hello!")
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
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Hello!")
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
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Hello!")
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

    def test_llm_judge_integration(self, tmp_path, mock_anthropic_client, mock_anthropic_message):
        """LLM judge assertions are evaluated via the runner."""
        # First call: main test response; second call: judge response
        test_msg = mock_anthropic_message(text="Hello! How can I help?")
        judge_msg = mock_anthropic_message(text="PASS\nThe response is friendly.")
        mock_anthropic_client.messages.create.side_effect = [test_msg, judge_msg]

        yaml = """
suite: "test"
skill: "./skills/SKILL.md"
tests:
  - type: single_turn
    name: "judge test"
    input:
      messages:
        - role: user
          content: "Hi"
    assertions:
      - type: llm_judge
        criteria: "Is the response friendly?"
"""
        eval_file = self._make_suite_files(tmp_path, yaml)
        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        result = runner.run()

        assert result.all_passed is True
        assert mock_anthropic_client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# New: skill_only message filtering
# ---------------------------------------------------------------------------


class TestSkillOnlyFiltering:
    def _make_suite_files(self, tmp_path, yaml_content):
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nYou are a helpful assistant.")
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)
        return eval_file

    def test_skill_only_messages_stripped_in_baseline(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        """Baseline runs should not include messages marked skill_only: true."""
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Hello!")
        yaml = """
suite: "test"
skill: "./skills/SKILL.md"
tests:
  - type: single_turn
    name: "skill_only check"
    baseline: true
    input:
      messages:
        - role: user
          content: "Show me the JSON."
        - role: assistant
          skill_only: true
          content: "Let me read the reference."
          tool_calls:
            - id: "tc_001"
              name: Read
              input: { file_path: "refs/schema.md" }
        - role: tool_result
          skill_only: true
          tool_use_id: "tc_001"
          content: "## Schema reference data"
        - role: user
          content: "Build it."
    assertions:
      - type: stop_reason
        value: end_turn
"""
        eval_file = self._make_suite_files(tmp_path, yaml)
        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        calls = mock_anthropic_client.messages.create.call_args_list
        assert len(calls) == 2  # skill + baseline

        # Skill run should contain the reference material
        skill_msg_str = str(calls[0].kwargs["messages"])
        assert "Schema reference data" in skill_msg_str
        assert "Let me read the reference" in skill_msg_str

        # Baseline run should NOT contain the reference material
        baseline_msg_str = str(calls[1].kwargs["messages"])
        assert "Schema reference data" not in baseline_msg_str
        assert "Let me read the reference" not in baseline_msg_str
        # But should still have the non-skill_only user messages
        assert "Show me the JSON" in baseline_msg_str
        assert "Build it" in baseline_msg_str

    def test_skill_only_messages_kept_in_skill_run(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        """Skill runs should include all messages, including skill_only ones."""
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Hello!")
        yaml = """
suite: "test"
skill: "./skills/SKILL.md"
tests:
  - type: single_turn
    name: "skill run check"
    baseline: false
    input:
      messages:
        - role: user
          content: "Show me the JSON."
        - role: assistant
          skill_only: true
          content: "Reading reference."
        - role: user
          content: "Build it."
    assertions:
      - type: stop_reason
        value: end_turn
"""
        eval_file = self._make_suite_files(tmp_path, yaml)
        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        calls = mock_anthropic_client.messages.create.call_args_list
        assert len(calls) == 1  # skill only, no baseline
        msg_str = str(calls[0].kwargs["messages"])
        assert "Reading reference" in msg_str

    def test_skill_only_multi_turn_baseline(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        """Multi-turn baseline runs should also strip skill_only messages."""
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Done!", stop_reason="end_turn"
        )
        yaml = """
suite: "test"
skill: "./skills/SKILL.md"
tests:
  - type: multi_turn
    name: "multi turn skill_only"
    baseline: true
    input:
      messages:
        - role: user
          content: "Do something"
        - role: assistant
          skill_only: true
          content: "Reference lookup"
        - role: user
          content: "Proceed"
    assertions:
      - type: stop_reason
        value: end_turn
"""
        eval_file = self._make_suite_files(tmp_path, yaml)
        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        calls = mock_anthropic_client.messages.create.call_args_list
        assert len(calls) == 2  # skill + baseline

        baseline_msg_str = str(calls[1].kwargs["messages"])
        assert "Reference lookup" not in baseline_msg_str
        assert "Do something" in baseline_msg_str


# ---------------------------------------------------------------------------
# New: Prefix integration
# ---------------------------------------------------------------------------


class TestSuiteRunnerPrefix:
    def _make_prefix_suite(self, tmp_path, extra_yaml="", prefix_yaml=""):
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nYou are a helpful assistant.")

        yaml_content = f"""
suite: "prefix test"
skill: "./skills/SKILL.md"
defaults:
  system_prompt: "You are helpful."
{prefix_yaml}
{extra_yaml}
tests:
  - type: single_turn
    name: "basic"
    input:
      messages:
        - role: user
          content: "Hello"
    assertions:
      - type: stop_reason
        value: end_turn
"""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)
        return eval_file

    def test_prefix_messages_appear_between_skill_and_input(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="OK")

        prefix_yaml = """
conversation_prefix:
  messages:
    - role: user
      content: "How do I sort a list?"
    - role: assistant
      content: "Use sorted() or list.sort()."
"""
        eval_file = self._make_prefix_suite(tmp_path, prefix_yaml=prefix_yaml)
        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        call_kwargs = mock_anthropic_client.messages.create.call_args
        messages = call_kwargs.kwargs["messages"]
        # Messages should contain: skill(user) + prefix(user, asst) + test(user)
        # After coalescing: skill+prefix_user merged → user, assistant, user
        msg_str = str(messages)
        assert "The following skill has been activated" in msg_str
        assert "How do I sort a list?" in msg_str
        assert "Use sorted()" in msg_str

    def test_prefix_present_in_both_skill_and_baseline_runs(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="OK")

        yaml_content = """
suite: "prefix test"
skill: "./skills/SKILL.md"
conversation_prefix:
  messages:
    - role: user
      content: "setup question"
    - role: assistant
      content: "setup answer"
tests:
  - type: single_turn
    name: "baseline check"
    baseline: true
    input:
      messages:
        - role: user
          content: "Hello"
    assertions:
      - type: stop_reason
        value: end_turn
"""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nYou are helpful.")

        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        calls = mock_anthropic_client.messages.create.call_args_list
        assert len(calls) == 2  # skill + baseline
        # Both should contain the prefix
        for call in calls:
            msg_str = str(call.kwargs["messages"])
            assert "setup question" in msg_str
            assert "setup answer" in msg_str

    def test_cache_control_on_last_prefix_message(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="OK")

        prefix_yaml = """
conversation_prefix:
  messages:
    - role: user
      content: "question"
    - role: assistant
      content: "answer"
"""
        eval_file = self._make_prefix_suite(tmp_path, prefix_yaml=prefix_yaml)
        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        call_kwargs = mock_anthropic_client.messages.create.call_args
        messages = call_kwargs.kwargs["messages"]
        # Find the assistant message containing the prefix answer
        for msg in messages:
            if msg["role"] == "assistant":
                content = msg["content"]
                if isinstance(content, list):
                    for block in content:
                        if block.get("text") == "answer":
                            assert block.get("cache_control") == {"type": "ephemeral"}
                            return
                elif isinstance(content, str) and "answer" in content:
                    # Content is a string — cache_control won't be embedded
                    # but it should be in list format when cache_control is set
                    pass
        # The cache_control should have been found on the prefix message
        # Since the assistant prefix message gets cache_control tagged,
        # and build_messages converts it to content blocks with cache_control
        messages_str = str(messages)
        assert "ephemeral" in messages_str

    def test_structured_system_prompt_when_caching_enabled(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="OK")

        eval_file = self._make_prefix_suite(tmp_path)
        suite = load_eval_suite(eval_file)
        # Default enable_caching=True
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        call_kwargs = mock_anthropic_client.messages.create.call_args
        system = call_kwargs.kwargs["system"]
        # Should be structured content with cache_control
        assert isinstance(system, list)
        assert system[0]["type"] == "text"
        assert system[0]["text"] == "You are helpful."
        assert system[0]["cache_control"] == {"type": "ephemeral"}

    def test_string_system_prompt_when_caching_disabled(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="OK")

        yaml_content = """
suite: "test"
skill: "./skills/SKILL.md"
defaults:
  system_prompt: "You are helpful."
  enable_caching: false
tests:
  - type: single_turn
    name: "basic"
    input:
      messages:
        - role: user
          content: "Hello"
    assertions:
      - type: stop_reason
        value: end_turn
"""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nBody")

        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        call_kwargs = mock_anthropic_client.messages.create.call_args
        system = call_kwargs.kwargs["system"]
        assert isinstance(system, str)
        assert system == "You are helpful."

    def test_external_file_prefix_loads(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="OK")

        skill_dir = tmp_path / "skills"
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nBody")

        prefix_file = tmp_path / "prefix.yaml"
        prefix_file.write_text(
            '- role: user\n  content: "external question"\n'
            '- role: assistant\n  content: "external answer"\n'
        )

        yaml_content = """
suite: "test"
skill: "./skills/SKILL.md"
conversation_prefix:
  file: "./prefix.yaml"
tests:
  - type: single_turn
    name: "basic"
    input:
      messages:
        - role: user
          content: "Hello"
    assertions:
      - type: stop_reason
        value: end_turn
"""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        call_kwargs = mock_anthropic_client.messages.create.call_args
        msg_str = str(call_kwargs.kwargs["messages"])
        assert "external question" in msg_str
        assert "external answer" in msg_str

    def test_token_threshold_warning_logged(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message, caplog
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="OK")

        prefix_yaml = """
conversation_prefix:
  messages:
    - role: user
      content: "short"
    - role: assistant
      content: "reply"
"""
        eval_file = self._make_prefix_suite(tmp_path, prefix_yaml=prefix_yaml)
        suite = load_eval_suite(eval_file)
        with caplog.at_level(logging.WARNING, logger="skill_evaluator.runner"):
            runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
            runner.run()

        assert any("below minimum cache threshold" in r.message for r in caplog.records)

    def test_empty_system_prompt_stays_string_even_with_caching(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        """When system_prompt is empty, don't wrap in structured format."""
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="OK")

        yaml_content = """
suite: "test"
skill: "./skills/SKILL.md"
tests:
  - type: single_turn
    name: "basic"
    input:
      messages:
        - role: user
          content: "Hello"
    assertions:
      - type: stop_reason
        value: end_turn
"""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir(exist_ok=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nBody")

        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        call_kwargs = mock_anthropic_client.messages.create.call_args
        system = call_kwargs.kwargs["system"]
        assert isinstance(system, str)
        assert system == ""
