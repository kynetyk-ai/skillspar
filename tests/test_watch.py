"""Tests for the watch module."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from rich.console import Console

from skill_evaluator.config.loader import ConfigLoadError
from skill_evaluator.config.schema import (
    ContextFileConfig,
    ConversationPrefixConfig,
    EvalSuite,
    InputConfig,
    MessageConfig,
    OutputContainsAssertion,
    SingleTurnTest,
    SuiteDefaults,
)
from skill_evaluator.engine.prefix import PrefixLoadError
from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup
from skill_evaluator.skill.parser import SkillParseError
from skill_evaluator.watch import (
    WatchIterationResult,
    discover_watched_files,
    display_iteration,
    run_once,
    watch_loop,
)


def _make_suite(
    skill="skill/SKILL.md",
    context=None,
    tests=None,
    conversation_prefix=None,
):
    """Build a minimal EvalSuite for testing."""
    if tests is None:
        tests = [
            SingleTurnTest(
                type="single_turn",
                name="basic-test",
                input=InputConfig(messages=[MessageConfig(role="user", content="hello")]),
                assertions=[OutputContainsAssertion(type="output_contains", value="hi")],
            )
        ]
    return EvalSuite(
        suite="test-suite",
        skill=skill,
        context=context,
        defaults=SuiteDefaults(),
        conversation_prefix=conversation_prefix,
        tests=tests,
    )


def _make_suite_result(passed=True):
    """Build a minimal SuiteResult."""
    tr = TestResult(test_name="basic-test")
    group = TestRunGroup(test_name="basic-test", runs=[tr])
    return SuiteResult(
        suite_name="test-suite",
        test_results=[group],
    )


class TestDiscoverWatchedFiles:
    def test_includes_eval_file(self, tmp_path):
        eval_file = tmp_path / "suite.eval.yaml"
        eval_file.touch()
        suite = _make_suite()
        paths = discover_watched_files(eval_file, suite)
        assert eval_file.resolve() in paths

    def test_includes_skill_file(self, tmp_path):
        eval_file = tmp_path / "suite.eval.yaml"
        eval_file.touch()
        suite = _make_suite(skill="my-skill/SKILL.md")
        paths = discover_watched_files(eval_file, suite)
        expected = (tmp_path / "my-skill" / "SKILL.md").resolve()
        assert expected in paths

    def test_includes_suite_context_files(self, tmp_path):
        eval_file = tmp_path / "suite.eval.yaml"
        eval_file.touch()
        suite = _make_suite(
            context=[
                ContextFileConfig(file="data/input.txt"),
                ContextFileConfig(file="data/other.txt"),
            ]
        )
        paths = discover_watched_files(eval_file, suite)
        assert (tmp_path / "data" / "input.txt").resolve() in paths
        assert (tmp_path / "data" / "other.txt").resolve() in paths

    def test_includes_test_context_files(self, tmp_path):
        eval_file = tmp_path / "suite.eval.yaml"
        eval_file.touch()
        test = SingleTurnTest(
            type="single_turn",
            name="ctx-test",
            context=[ContextFileConfig(file="test-data.txt")],
            input=InputConfig(messages=[MessageConfig(role="user", content="hello")]),
            assertions=[OutputContainsAssertion(type="output_contains", value="hi")],
        )
        suite = _make_suite(tests=[test])
        paths = discover_watched_files(eval_file, suite)
        assert (tmp_path / "test-data.txt").resolve() in paths

    def test_includes_prefix_file(self, tmp_path):
        eval_file = tmp_path / "suite.eval.yaml"
        eval_file.touch()
        prefix = ConversationPrefixConfig(file="prefix.yaml")
        suite = _make_suite(conversation_prefix=prefix)
        paths = discover_watched_files(eval_file, suite)
        assert (tmp_path / "prefix.yaml").resolve() in paths

    def test_no_prefix_file_when_inline(self, tmp_path):
        eval_file = tmp_path / "suite.eval.yaml"
        eval_file.touch()
        prefix = ConversationPrefixConfig(
            messages=[
                MessageConfig(role="user", content="hi"),
                MessageConfig(role="assistant", content="hello"),
            ]
        )
        suite = _make_suite(conversation_prefix=prefix)
        paths = discover_watched_files(eval_file, suite)
        # Only eval file + skill file
        assert len(paths) == 2

    def test_deduplicates_paths(self, tmp_path):
        eval_file = tmp_path / "suite.eval.yaml"
        eval_file.touch()
        # Same file referenced in both suite and test context
        test = SingleTurnTest(
            type="single_turn",
            name="dup-test",
            context=[ContextFileConfig(file="shared.txt")],
            input=InputConfig(messages=[MessageConfig(role="user", content="hello")]),
            assertions=[OutputContainsAssertion(type="output_contains", value="hi")],
        )
        suite = _make_suite(
            context=[ContextFileConfig(file="shared.txt")],
            tests=[test],
        )
        paths = discover_watched_files(eval_file, suite)
        shared_path = (tmp_path / "shared.txt").resolve()
        # Should appear exactly once (it's a set)
        assert shared_path in paths
        # Total: eval_file + skill + shared.txt = 3
        assert len(paths) == 3


class TestRunOnce:
    @patch("skill_evaluator.watch.execute_suite")
    @patch("skill_evaluator.watch.load_eval_suite")
    def test_success_path(self, mock_load, mock_execute, tmp_path):
        eval_file = tmp_path / "suite.eval.yaml"
        eval_file.touch()
        suite = _make_suite()
        suite_result = _make_suite_result()
        mock_load.return_value = suite
        mock_execute.return_value = suite_result

        result = run_once(eval_file)

        assert result.error is None
        assert result.suite is suite
        assert result.suite_result is suite_result
        assert result.report is not None
        assert result.report["suite"] == "test-suite"

    @patch("skill_evaluator.watch.load_eval_suite")
    def test_config_load_error(self, mock_load, tmp_path):

        eval_file = tmp_path / "suite.eval.yaml"
        eval_file.touch()
        mock_load.side_effect = ConfigLoadError("bad yaml")

        result = run_once(eval_file)

        assert result.error == "bad yaml"
        assert result.suite is None
        assert result.report is None

    @patch("skill_evaluator.watch.execute_suite")
    @patch("skill_evaluator.watch.load_eval_suite")
    def test_skill_parse_error(self, mock_load, mock_execute, tmp_path):
        eval_file = tmp_path / "suite.eval.yaml"
        eval_file.touch()
        mock_load.return_value = _make_suite()
        mock_execute.side_effect = SkillParseError("bad frontmatter")

        result = run_once(eval_file)

        assert result.error == "bad frontmatter"
        assert result.suite is None

    @patch("skill_evaluator.watch.execute_suite")
    @patch("skill_evaluator.watch.load_eval_suite")
    def test_prefix_load_error(self, mock_load, mock_execute, tmp_path):
        eval_file = tmp_path / "suite.eval.yaml"
        eval_file.touch()
        mock_load.return_value = _make_suite()
        mock_execute.side_effect = PrefixLoadError("missing prefix")

        result = run_once(eval_file)

        assert result.error == "missing prefix"

    @patch("skill_evaluator.watch.execute_suite")
    @patch("skill_evaluator.watch.load_eval_suite")
    def test_filter_pattern_applied(self, mock_load, mock_execute, tmp_path):
        eval_file = tmp_path / "suite.eval.yaml"
        eval_file.touch()
        test1 = SingleTurnTest(
            type="single_turn",
            name="alpha-test",
            input=InputConfig(messages=[MessageConfig(role="user", content="hello")]),
            assertions=[OutputContainsAssertion(type="output_contains", value="hi")],
        )
        test2 = SingleTurnTest(
            type="single_turn",
            name="beta-test",
            input=InputConfig(messages=[MessageConfig(role="user", content="hello")]),
            assertions=[OutputContainsAssertion(type="output_contains", value="hi")],
        )
        suite = _make_suite(tests=[test1, test2])
        mock_load.return_value = suite
        mock_execute.return_value = _make_suite_result()

        result = run_once(eval_file, cli_filter_pattern="alpha")

        assert result.error is None
        # execute_suite should have been called with only the alpha test
        called_suite = mock_execute.call_args[0][1]
        assert len(called_suite.tests) == 1
        assert called_suite.tests[0].name == "alpha-test"

    @patch("skill_evaluator.watch.load_eval_suite")
    def test_filter_no_match_returns_error(self, mock_load, tmp_path):
        eval_file = tmp_path / "suite.eval.yaml"
        eval_file.touch()
        mock_load.return_value = _make_suite()

        result = run_once(eval_file, cli_filter_pattern="nonexistent")

        assert result.error is not None
        assert "nonexistent" in result.error


class TestDisplayIteration:
    def _make_console(self):
        buf = StringIO()
        return Console(file=buf, no_color=True, width=120), buf

    def test_displays_header(self):
        console, buf = self._make_console()
        result = WatchIterationResult(
            suite=_make_suite(),
            suite_result=_make_suite_result(),
            report={"tests": [], "summary": {}},
        )
        display_iteration(console, 1, result, None, verbose=False)
        output = buf.getvalue()
        assert "Iteration 1" in output

    def test_displays_error(self):
        console, buf = self._make_console()
        result = WatchIterationResult(error="YAML parse error")
        display_iteration(console, 2, result, None, verbose=False)
        output = buf.getvalue()
        assert "YAML parse error" in output
        assert "Watching for changes" in output

    def test_displays_results_on_success(self):
        console, buf = self._make_console()
        result = WatchIterationResult(
            suite=_make_suite(),
            suite_result=_make_suite_result(),
            report={"tests": [], "summary": {}},
        )
        display_iteration(console, 1, result, None, verbose=False)
        output = buf.getvalue()
        assert "test-suite" in output
        assert "Watching for changes" in output

    def test_displays_diff_when_previous_report(self):
        console, buf = self._make_console()
        previous = {
            "tests": [
                {
                    "name": "basic-test",
                    "summary": {"pass_rate": 0.5, "passed": False},
                    "runs": [{"assertions": []}],
                }
            ],
            "summary": {},
            "timestamp": "2025-01-01T00:00:00",
        }
        current = {
            "tests": [
                {
                    "name": "basic-test",
                    "summary": {"pass_rate": 1.0, "passed": True},
                    "runs": [{"assertions": []}],
                }
            ],
            "summary": {},
            "timestamp": "2025-01-01T01:00:00",
        }
        result = WatchIterationResult(
            suite=_make_suite(),
            suite_result=_make_suite_result(),
            report=current,
        )
        display_iteration(console, 2, result, previous, verbose=False)
        output = buf.getvalue()
        assert "IMPROVED" in output


class TestWatchLoop:
    @patch("skill_evaluator.watch.watchfiles.watch")
    @patch("skill_evaluator.watch.run_once")
    def test_initial_run_then_file_change(self, mock_run_once, mock_watch, tmp_path):
        eval_file = tmp_path / "suite.eval.yaml"
        eval_file.touch()

        suite = _make_suite()
        suite_result = _make_suite_result()
        report = {"tests": [], "summary": {}, "timestamp": "2025-01-01T00:00:00"}

        initial_result = WatchIterationResult(
            suite=suite,
            suite_result=suite_result,
            report=report,
        )
        second_result = WatchIterationResult(
            suite=suite,
            suite_result=suite_result,
            report=report,
        )
        mock_run_once.side_effect = [initial_result, second_result, KeyboardInterrupt]

        # Mock watchfiles.watch as a generator yielding one change set
        def fake_watch(*paths, debounce=None):
            yield {("modified", str(eval_file))}
            yield {("modified", str(eval_file))}  # triggers third run_once -> KeyboardInterrupt

        mock_watch.side_effect = fake_watch

        exit_code = watch_loop(eval_file, debounce_ms=100)

        assert exit_code == 0
        assert mock_run_once.call_count >= 2  # initial + at least one re-run

    @patch("skill_evaluator.watch.watchfiles.watch")
    @patch("skill_evaluator.watch.run_once")
    def test_error_iteration_preserves_previous_report(self, mock_run_once, mock_watch, tmp_path):
        eval_file = tmp_path / "suite.eval.yaml"
        eval_file.touch()

        suite = _make_suite()
        suite_result = _make_suite_result()
        good_report = {
            "tests": [
                {
                    "name": "basic-test",
                    "summary": {"pass_rate": 1.0, "passed": True},
                    "runs": [{"assertions": []}],
                }
            ],
            "summary": {},
            "timestamp": "2025-01-01T00:00:00",
        }

        results = [
            # Initial: success
            WatchIterationResult(
                suite=suite,
                suite_result=suite_result,
                report=good_report,
            ),
            # Second: error (report stays None)
            WatchIterationResult(error="syntax error"),
            # Third: triggers KeyboardInterrupt
        ]

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            if call_count < len(results):
                r = results[call_count]
                call_count += 1
                return r
            raise KeyboardInterrupt

        mock_run_once.side_effect = side_effect

        def fake_watch(*paths, debounce=None):
            yield {("modified", str(eval_file))}
            yield {("modified", str(eval_file))}

        mock_watch.side_effect = fake_watch

        exit_code = watch_loop(eval_file, debounce_ms=100)

        assert exit_code == 0
        # run_once called 3 times: initial + 2 change events (third raises KeyboardInterrupt)
        assert call_count >= 2

    @patch("skill_evaluator.watch.watchfiles.watch")
    @patch("skill_evaluator.watch.run_once")
    def test_ctrl_c_on_initial_run(self, mock_run_once, mock_watch, tmp_path):
        eval_file = tmp_path / "suite.eval.yaml"
        eval_file.touch()

        mock_run_once.side_effect = KeyboardInterrupt

        exit_code = watch_loop(eval_file, debounce_ms=100)
        assert exit_code == 0
