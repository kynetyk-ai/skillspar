"""Pydantic models for the .eval.yaml test definition schema."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

class StopReasonAssertion(BaseModel):
    type: Literal["stop_reason"]
    value: str


class OutputContainsAssertion(BaseModel):
    type: Literal["output_contains"]
    value: str


class OutputNotContainsAssertion(BaseModel):
    type: Literal["output_not_contains"]
    value: str


class OutputMatchesRegexAssertion(BaseModel):
    type: Literal["output_matches_regex"]
    pattern: str

    @field_validator("pattern")
    @classmethod
    def validate_regex(cls, v: str) -> str:
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}") from e
        return v


class ToolCalledAssertion(BaseModel):
    type: Literal["tool_called"]
    tool: str


class ToolNotCalledAssertion(BaseModel):
    type: Literal["tool_not_called"]
    tool: str


# Phase 2+ stubs — parse but don't execute yet

class ToolCalledTimesAssertion(BaseModel):
    type: Literal["tool_called_times"]
    tool: str
    min: int | None = None
    max: int | None = None
    exactly: int | None = None


class ToolArgsMatchAssertion(BaseModel):
    type: Literal["tool_args_match"]
    tool: str
    path: str
    pattern: str


class ToolSequenceAssertion(BaseModel):
    type: Literal["tool_sequence"]
    tools: list[str]


class TurnCountAssertion(BaseModel):
    type: Literal["turn_count"]
    min: int | None = None
    max: int | None = None
    exactly: int | None = None


class LLMJudgeAssertion(BaseModel):
    type: Literal["llm_judge"]
    criteria: str
    model: str | None = None


AssertionConfig = Annotated[
    Union[
        StopReasonAssertion,
        OutputContainsAssertion,
        OutputNotContainsAssertion,
        OutputMatchesRegexAssertion,
        ToolCalledAssertion,
        ToolNotCalledAssertion,
        ToolCalledTimesAssertion,
        ToolArgsMatchAssertion,
        ToolSequenceAssertion,
        TurnCountAssertion,
        LLMJudgeAssertion,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Messages / Input
# ---------------------------------------------------------------------------

class ToolCallConfig(BaseModel):
    id: str
    name: str
    input: dict[str, Any]


class MessageConfig(BaseModel):
    role: Literal["user", "assistant", "tool_result"]
    content: str | None = None
    tool_calls: list[ToolCallConfig] | None = None
    tool_use_id: str | None = None


class InputConfig(BaseModel):
    messages: list[MessageConfig]


# ---------------------------------------------------------------------------
# Tools (forward-compat)
# ---------------------------------------------------------------------------

class BuiltinToolConfig(BaseModel):
    builtin: str


class CustomToolConfig(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


ToolConfig = Union[BuiltinToolConfig, CustomToolConfig]


# ---------------------------------------------------------------------------
# Tool responses (forward-compat for multi-turn)
# ---------------------------------------------------------------------------

class ToolMatchConfig(BaseModel):
    tool: str | None = None


class ToolResponseConfig(BaseModel):
    match: ToolMatchConfig | str
    response: dict[str, Any] | None = None
    responses: list[dict[str, Any]] | None = None

    @model_validator(mode="after")
    def validate_response_fields(self) -> ToolResponseConfig:
        has_response = self.response is not None
        has_responses = self.responses is not None
        if has_response and has_responses:
            raise ValueError("Specify either 'response' or 'responses', not both")
        if not has_response and not has_responses:
            raise ValueError("One of 'response' or 'responses' is required")
        if has_responses and len(self.responses) == 0:
            raise ValueError("'responses' must not be empty")
        return self

    def get_response(self, call_index: int = 0) -> dict[str, Any]:
        if self.response is not None:
            return self.response
        clamped = min(call_index, len(self.responses) - 1)
        return self.responses[clamped]


# ---------------------------------------------------------------------------
# Context Files
# ---------------------------------------------------------------------------

class ContextFileConfig(BaseModel):
    file: str
    lines: list[int] | None = None

    @field_validator("lines")
    @classmethod
    def validate_lines(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        if len(v) != 2:
            raise ValueError("lines must be [start, end]")
        if v[0] < 1:
            raise ValueError("start must be >= 1")
        if v[1] < v[0]:
            raise ValueError("end must be >= start")
        return v


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class SingleTurnTest(BaseModel):
    type: Literal["single_turn"]
    name: str
    context: list[ContextFileConfig] | None = None
    input: InputConfig
    assertions: list[AssertionConfig]
    runs: int | None = None
    pass_threshold: float | None = None
    baseline: bool = False


class MultiTurnTest(BaseModel):
    type: Literal["multi_turn"]
    name: str
    context: list[ContextFileConfig] | None = None
    input: InputConfig
    max_turns: int = 10
    tool_responses: list[ToolResponseConfig] | None = None
    assertions: list[AssertionConfig]
    runs: int | None = None
    pass_threshold: float | None = None
    baseline: bool = False


TestConfig = Annotated[
    Union[SingleTurnTest, MultiTurnTest],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------

class SuiteDefaults(BaseModel):
    model: str = "claude-sonnet-4-5-20250929"
    judge_model: str = ""
    max_tokens: int = 4096
    temperature: float = 0
    runs: int = 1
    pass_threshold: float = 1.0
    max_retries: int = 2
    concurrency: int = 1

    @field_validator("runs")
    @classmethod
    def validate_runs(cls, v: int) -> int:
        if v < 1:
            raise ValueError("runs must be >= 1")
        return v

    @field_validator("pass_threshold")
    @classmethod
    def validate_pass_threshold(cls, v: float) -> float:
        if v <= 0.0 or v > 1.0:
            raise ValueError("pass_threshold must be in (0.0, 1.0]")
        return v

    @field_validator("concurrency")
    @classmethod
    def validate_concurrency(cls, v: int) -> int:
        if v < 1:
            raise ValueError("concurrency must be >= 1")
        return v

    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        if v < 0:
            raise ValueError("max_retries must be >= 0")
        return v


class EvalSuite(BaseModel):
    suite: str
    skill: str
    context: list[ContextFileConfig] | None = None
    defaults: SuiteDefaults = SuiteDefaults()
    tools: list[ToolConfig] | None = None
    tests: list[TestConfig]


# ---------------------------------------------------------------------------
# Resolved Config — single source of truth after all layers merge
# ---------------------------------------------------------------------------


class ResolvedConfig(BaseModel, frozen=True):
    """Frozen config produced by merging defaults → env vars → YAML → CLI flags."""

    model: str = "claude-sonnet-4-5-20250929"
    judge_model: str = ""
    max_tokens: int = 4096
    temperature: float = 0
    runs: int = 1
    pass_threshold: float = 1.0
    max_retries: int = 2
    concurrency: int = 1
    output: str | None = None
    output_format: str = "json"
    verbose: bool = False
    filter_pattern: str | None = None
