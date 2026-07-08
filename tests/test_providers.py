"""Tests for providers/ — adapter protocol, Anthropic and OpenAI-compat adapters."""

import json
from unittest.mock import MagicMock, patch

import pytest

from skill_evaluator.providers import (
    DEFAULT_API_KEY_ENV,
    ProviderError,
    get_provider,
    missing_api_key_error,
)
from skill_evaluator.providers.anthropic import AnthropicProvider
from skill_evaluator.providers.openai_compat import OpenAICompatProvider


def _create(provider, **overrides):
    kwargs = {
        "model": "test-model",
        "system": "sys",
        "messages": [{"role": "user", "content": "hi"}],
        "tools": None,
        "max_tokens": 100,
        "temperature": 0,
    }
    kwargs.update(overrides)
    return provider.create_message(**kwargs)


class TestGetProvider:
    def test_builds_anthropic(self, mock_anthropic_client):
        provider = get_provider("anthropic", client=mock_anthropic_client)
        assert isinstance(provider, AnthropicProvider)
        assert provider.name == "anthropic"

    def test_builds_openai(self, mock_openai_client):
        provider = get_provider("openai", client=mock_openai_client)
        assert isinstance(provider, OpenAICompatProvider)
        assert provider.name == "openai"

    def test_unknown_provider_raises(self):
        with pytest.raises(ProviderError, match="Unknown provider"):
            get_provider("gemini")


class TestMissingApiKeyError:
    def test_returns_message_when_unset(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        message = missing_api_key_error("openai")
        assert message is not None
        assert "OPENAI_API_KEY" in message

    def test_returns_none_when_set(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        assert missing_api_key_error("openai") is None

    def test_custom_env_name(self, monkeypatch):
        monkeypatch.delenv("MY_KEY", raising=False)
        message = missing_api_key_error("openai", api_key_env="MY_KEY")
        assert message is not None
        assert "MY_KEY" in message

    def test_default_env_map(self):
        assert DEFAULT_API_KEY_ENV["anthropic"] == "ANTHROPIC_API_KEY"
        assert DEFAULT_API_KEY_ENV["openai"] == "OPENAI_API_KEY"


class TestAnthropicProvider:
    def test_kwargs_passthrough(self, mock_anthropic_client):
        provider = AnthropicProvider(mock_anthropic_client)
        _create(provider, tools=[{"name": "Read", "input_schema": {}}])

        kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert kwargs["model"] == "test-model"
        assert kwargs["system"] == "sys"
        assert kwargs["max_tokens"] == 100
        assert kwargs["temperature"] == 0
        assert kwargs["tools"] == [{"name": "Read", "input_schema": {}}]

    def test_omits_temperature_when_none(self, mock_anthropic_client):
        provider = AnthropicProvider(mock_anthropic_client)
        _create(provider, temperature=None)
        assert "temperature" not in mock_anthropic_client.messages.create.call_args.kwargs

    def test_omits_tools_when_empty(self, mock_anthropic_client):
        provider = AnthropicProvider(mock_anthropic_client)
        _create(provider, tools=None)
        assert "tools" not in mock_anthropic_client.messages.create.call_args.kwargs

    def test_cache_control_passes_through(self, mock_anthropic_client):
        provider = AnthropicProvider(mock_anthropic_client)
        system = [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}]
        _create(provider, system=system)
        assert mock_anthropic_client.messages.create.call_args.kwargs["system"] == system

    def test_returns_normalized_turn(self, mock_anthropic_client, mock_anthropic_message):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Hi!", stop_reason="end_turn"
        )
        provider = AnthropicProvider(mock_anthropic_client)
        turn = _create(provider)
        assert turn.text_output == "Hi!"
        assert turn.stop_reason == "end_turn"
        assert turn.usage.input_tokens == 100

    def test_api_error_wrapped(self, mock_anthropic_client):
        from anthropic import APIConnectionError

        mock_anthropic_client.messages.create.side_effect = APIConnectionError(request=MagicMock())
        provider = AnthropicProvider(mock_anthropic_client)
        with pytest.raises(ProviderError):
            _create(provider)


class TestOpenAIRequestTranslation:
    def test_system_string_becomes_system_message(self, mock_openai_client):
        provider = OpenAICompatProvider(mock_openai_client)
        _create(provider, system="be helpful")
        messages = mock_openai_client.chat.completions.create.call_args.kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "be helpful"}

    def test_system_blocks_flattened(self, mock_openai_client):
        provider = OpenAICompatProvider(mock_openai_client)
        system = [{"type": "text", "text": "be helpful", "cache_control": {"type": "ephemeral"}}]
        _create(provider, system=system)
        messages = mock_openai_client.chat.completions.create.call_args.kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "be helpful"}

    def test_empty_system_omitted(self, mock_openai_client):
        provider = OpenAICompatProvider(mock_openai_client)
        _create(provider, system="")
        messages = mock_openai_client.chat.completions.create.call_args.kwargs["messages"]
        assert messages[0]["role"] == "user"

    def test_tool_result_becomes_tool_message(self, mock_openai_client):
        provider = OpenAICompatProvider(mock_openai_client)
        _create(
            provider,
            messages=[
                {"role": "user", "content": "hi"},
                {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "tc_1", "name": "Read", "input": {"f": "x"}}
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "tc_1", "content": "file data"}
                    ],
                },
            ],
        )
        messages = mock_openai_client.chat.completions.create.call_args.kwargs["messages"]
        assistant = messages[2]  # [0]=system, [1]=user
        assert assistant["role"] == "assistant"
        assert assistant["tool_calls"][0]["id"] == "tc_1"
        assert assistant["tool_calls"][0]["function"]["name"] == "Read"
        assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {"f": "x"}
        tool_msg = messages[3]
        assert tool_msg == {"role": "tool", "tool_call_id": "tc_1", "content": "file data"}

    def test_cache_control_stripped(self, mock_openai_client):
        provider = OpenAICompatProvider(mock_openai_client)
        _create(
            provider,
            system="",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "hi",
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                }
            ],
        )
        messages = mock_openai_client.chat.completions.create.call_args.kwargs["messages"]
        assert messages == [{"role": "user", "content": "hi"}]

    def test_tools_schema_mapped(self, mock_openai_client):
        provider = OpenAICompatProvider(mock_openai_client)
        schema = {"type": "object", "properties": {"f": {"type": "string"}}}
        _create(
            provider,
            tools=[{"name": "Read", "description": "read a file", "input_schema": schema}],
        )
        tools = mock_openai_client.chat.completions.create.call_args.kwargs["tools"]
        assert tools == [
            {
                "type": "function",
                "function": {
                    "name": "Read",
                    "description": "read a file",
                    "parameters": schema,
                },
            }
        ]


class TestOpenAIResponseTranslation:
    @pytest.mark.parametrize(
        ("finish_reason", "expected"),
        [
            ("stop", "end_turn"),
            ("tool_calls", "tool_use"),
            ("length", "max_tokens"),
            ("content_filter", "content_filter"),
        ],
    )
    def test_finish_reason_map(
        self, mock_openai_client, mock_openai_completion, finish_reason, expected
    ):
        mock_openai_client.chat.completions.create.return_value = mock_openai_completion(
            finish_reason=finish_reason
        )
        provider = OpenAICompatProvider(mock_openai_client)
        assert _create(provider).stop_reason == expected

    def test_tool_calls_parsed(self, mock_openai_client, mock_openai_completion):
        mock_openai_client.chat.completions.create.return_value = mock_openai_completion(
            text=None,
            tool_calls=[{"id": "tc_1", "name": "Read", "arguments": '{"f": "x"}'}],
            finish_reason="tool_calls",
        )
        provider = OpenAICompatProvider(mock_openai_client)
        turn = _create(provider)
        assert turn.text_output == ""
        assert len(turn.tool_calls) == 1
        assert turn.tool_calls[0].id == "tc_1"
        assert turn.tool_calls[0].name == "Read"
        assert turn.tool_calls[0].input == {"f": "x"}

    def test_malformed_arguments_degrade_to_empty(self, mock_openai_client, mock_openai_completion):
        mock_openai_client.chat.completions.create.return_value = mock_openai_completion(
            tool_calls=[{"id": "tc_1", "name": "Read", "arguments": "not json"}],
            finish_reason="tool_calls",
        )
        provider = OpenAICompatProvider(mock_openai_client)
        turn = _create(provider)
        assert turn.tool_calls[0].input == {}

    def test_usage_mapped(self, mock_openai_client, mock_openai_completion):
        mock_openai_client.chat.completions.create.return_value = mock_openai_completion(
            cached_tokens=40
        )
        provider = OpenAICompatProvider(mock_openai_client)
        turn = _create(provider)
        assert turn.usage.input_tokens == 100
        assert turn.usage.output_tokens == 50
        assert turn.usage.cache_read_input_tokens == 40
        assert turn.usage.cache_creation_input_tokens is None

    def test_usage_without_cached_tokens(self, mock_openai_client, mock_openai_completion):
        mock_openai_client.chat.completions.create.return_value = mock_openai_completion()
        provider = OpenAICompatProvider(mock_openai_client)
        assert _create(provider).usage.cache_read_input_tokens is None

    def test_api_error_wrapped(self, mock_openai_client):
        mock_openai_client.chat.completions.create.side_effect = RuntimeError("boom")
        provider = OpenAICompatProvider(mock_openai_client)
        with pytest.raises(ProviderError, match="API call failed"):
            _create(provider)


class TestOpenAIMissingSdk:
    def test_missing_sdk_raises_provider_error(self):
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(ProviderError, match="skillspar\\[openai\\]"):
                OpenAICompatProvider()


class TestMultiTurnWithOpenAI:
    def test_tool_loop_over_openai_provider(self, mock_openai_client, mock_openai_completion):
        from skill_evaluator.config.schema import (
            InputConfig,
            MessageConfig,
            ResolvedConfig,
            ToolMatchConfig,
            ToolResponseConfig,
        )
        from skill_evaluator.engine.multi_turn import MultiTurnExecutor

        mock_openai_client.chat.completions.create.side_effect = [
            mock_openai_completion(
                text="Reading...",
                tool_calls=[{"id": "tc_1", "name": "Read", "arguments": '{"file": "a.txt"}'}],
                finish_reason="tool_calls",
            ),
            mock_openai_completion(text="Done!", finish_reason="stop"),
        ]
        provider = OpenAICompatProvider(mock_openai_client)
        executor = MultiTurnExecutor(
            provider=provider,
            config=ResolvedConfig(provider="openai"),
            tools=[{"name": "Read", "description": "", "input_schema": {"type": "object"}}],
            tool_responses=[
                ToolResponseConfig(
                    match=ToolMatchConfig(tool="Read"), response={"content": "file contents"}
                )
            ],
        )
        trace = executor.execute(
            "sys", InputConfig(messages=[MessageConfig(role="user", content="read a.txt")])
        )

        assert trace.turn_count == 2
        assert trace.tool_names == ["Read"]
        assert trace.stop_reason == "end_turn"
        # Second call must include the echoed assistant tool_calls and the tool reply
        second_messages = mock_openai_client.chat.completions.create.call_args.kwargs["messages"]
        roles = [m["role"] for m in second_messages]
        assert roles == ["system", "user", "assistant", "tool"]


class TestProviderConfig:
    def test_defaults(self):
        from skill_evaluator.config.schema import SuiteDefaults

        d = SuiteDefaults()
        assert d.provider == "anthropic"
        assert d.base_url is None
        assert d.api_key_env is None
        assert d.judge_provider is None

    def test_invalid_provider_rejected(self):
        from pydantic import ValidationError

        from skill_evaluator.config.schema import SuiteDefaults

        with pytest.raises(ValidationError):
            SuiteDefaults(provider="gemini")

    def test_cross_provider_judge_requires_judge_model(self):
        from pydantic import ValidationError

        from skill_evaluator.config.schema import SuiteDefaults

        with pytest.raises(ValidationError, match="judge_model is required"):
            SuiteDefaults(provider="openai", judge_provider="anthropic")

    def test_cross_provider_judge_with_model_ok(self):
        from skill_evaluator.config.schema import SuiteDefaults

        d = SuiteDefaults(
            provider="openai", judge_provider="anthropic", judge_model="claude-sonnet-4-5"
        )
        assert d.judge_provider == "anthropic"

    def test_env_var_injection(self, monkeypatch, tmp_path):
        from skill_evaluator.config.loader import load_eval_suite

        monkeypatch.setenv("SKILLSPAR_PROVIDER", "openai")
        monkeypatch.setenv("SKILLSPAR_BASE_URL", "http://localhost:11434/v1")

        (tmp_path / "SKILL.md").write_text("---\nname: t\n---\nBody")
        eval_file = tmp_path / "t.eval.yaml"
        eval_file.write_text(
            "suite: t\nskill: ./SKILL.md\ntests:\n"
            "  - name: t\n    type: single_turn\n"
            "    input:\n      messages:\n        - role: user\n          content: hi\n"
            "    assertions:\n      - type: output_contains\n        value: hi\n"
        )
        suite = load_eval_suite(eval_file)
        assert suite.defaults.provider == "openai"
        assert suite.defaults.base_url == "http://localhost:11434/v1"

    def test_yaml_beats_env(self, monkeypatch, tmp_path):
        from skill_evaluator.config.loader import load_eval_suite

        monkeypatch.setenv("SKILLSPAR_PROVIDER", "openai")
        (tmp_path / "SKILL.md").write_text("---\nname: t\n---\nBody")
        eval_file = tmp_path / "t.eval.yaml"
        eval_file.write_text(
            "suite: t\nskill: ./SKILL.md\ndefaults:\n  provider: anthropic\ntests:\n"
            "  - name: t\n    type: single_turn\n"
            "    input:\n      messages:\n        - role: user\n          content: hi\n"
            "    assertions:\n      - type: output_contains\n        value: hi\n"
        )
        assert load_eval_suite(eval_file).defaults.provider == "anthropic"

    def test_cli_flag_beats_yaml(self):
        from skill_evaluator.config.loader import resolve_config
        from skill_evaluator.config.schema import SuiteDefaults

        config = resolve_config(
            SuiteDefaults(provider="anthropic"),
            cli_provider="openai",
            cli_base_url="http://localhost:8000/v1",
        )
        assert config.provider == "openai"
        assert config.base_url == "http://localhost:8000/v1"


class TestRunnerProviders:
    def test_separate_judge_provider(self, tmp_path, mock_openai_client):
        from skill_evaluator.config.schema import EvalSuite, ResolvedConfig
        from skill_evaluator.runner import SuiteRunner

        suite = EvalSuite.model_validate(
            {
                "suite": "t",
                "skill": "./SKILL.md",
                "tests": [
                    {
                        "name": "t",
                        "type": "single_turn",
                        "input": {"messages": [{"role": "user", "content": "hi"}]},
                        "assertions": [{"type": "output_contains", "value": "hi"}],
                    }
                ],
            }
        )
        config = ResolvedConfig(
            provider="openai", judge_provider="anthropic", judge_model="claude-sonnet-4-5"
        )
        runner = SuiteRunner(
            tmp_path / "t.eval.yaml", suite, client=mock_openai_client, config=config
        )
        assert runner.provider.name == "openai"
        assert runner.judge_provider.name == "anthropic"
        assert runner.provider is not runner.judge_provider

    def test_same_provider_shares_instance(self, tmp_path, mock_anthropic_client):
        from skill_evaluator.config.schema import EvalSuite, ResolvedConfig
        from skill_evaluator.runner import SuiteRunner

        suite = EvalSuite.model_validate(
            {
                "suite": "t",
                "skill": "./SKILL.md",
                "tests": [],
            }
        )
        runner = SuiteRunner(
            tmp_path / "t.eval.yaml",
            suite,
            client=mock_anthropic_client,
            config=ResolvedConfig(),
        )
        assert runner.judge_provider is runner.provider


class TestOpenAICostSemantics:
    def test_openai_cache_semantics(self, monkeypatch, tmp_path):
        from skill_evaluator.engine.trace import TokenUsage
        from skill_evaluator.reporting.cost import estimate_cost

        pricing = {
            "gpt-test": {
                "input": 2.0,
                "output": 8.0,
                "cache_read_multiplier": 0.5,
                "cache_semantics": "openai",
            }
        }
        pricing_file = tmp_path / "pricing.json"
        pricing_file.write_text(json.dumps(pricing))
        monkeypatch.setenv("SKILLSPAR_PRICING_FILE", str(pricing_file))

        # 1000 input (400 of them cached reads), 500 output
        usage = TokenUsage(input_tokens=1000, output_tokens=500, cache_read_input_tokens=400)
        cost = estimate_cost(usage, "gpt-test")
        expected = (600 * 2.0 + 400 * 2.0 * 0.5 + 500 * 8.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_anthropic_semantics_unchanged(self):
        from skill_evaluator.engine.trace import TokenUsage
        from skill_evaluator.reporting.cost import estimate_cost

        usage = TokenUsage(input_tokens=1000, output_tokens=500)
        cost = estimate_cost(usage, "claude-sonnet-4-5-20250929")
        assert cost == pytest.approx((1000 * 3.0 + 500 * 15.0) / 1_000_000)


class TestStopReasonAliases:
    @pytest.mark.parametrize("value", ["end_turn", "stop"])
    def test_aliases_match_canonical_trace(self, simple_text_trace, value):
        from skill_evaluator.assertions.deterministic import check_stop_reason
        from skill_evaluator.config.schema import StopReasonAssertion

        result = check_stop_reason(
            StopReasonAssertion(type="stop_reason", value=value), simple_text_trace
        )
        assert result.status.value == "passed"
