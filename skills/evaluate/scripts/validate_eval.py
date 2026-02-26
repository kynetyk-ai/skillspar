#!/usr/bin/env python3
"""Validate a .eval.yaml file and produce LLM-friendly error messages.

Usage:
    python validate_eval.py <path-to-eval-yaml>

Standalone script — requires only PyYAML (no skill_evaluator package needed).
Validates schema structure and catches common semantic mistakes, producing
actionable fix instructions designed for LLM consumption.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_TEST_TYPES = ["single_turn", "multi_turn"]
VALID_ASSERTION_TYPES = [
    "output_contains",
    "output_not_contains",
    "output_matches_regex",
    "tool_called",
    "tool_not_called",
    "tool_called_times",
    "tool_args_match",
    "tool_sequence",
    "turn_count",
    "llm_judge",
    "stop_reason",
]
VALID_MESSAGE_ROLES = ["user", "assistant", "tool_result"]

# Required fields per assertion type (beyond "type" itself)
ASSERTION_REQUIRED_FIELDS: dict[str, list[tuple[str, type | tuple[type, ...]]]] = {
    "stop_reason": [("value", str)],
    "output_contains": [("value", str)],
    "output_not_contains": [("value", str)],
    "output_matches_regex": [("pattern", str)],
    "tool_called": [("tool", str)],
    "tool_not_called": [("tool", str)],
    "tool_called_times": [("tool", str)],
    "tool_args_match": [("tool", str), ("path", str), ("pattern", str)],
    "tool_sequence": [("tools", list)],
    "turn_count": [],
    "llm_judge": [("criteria", str)],
}

# All valid fields per assertion type (for unknown-field detection)
ASSERTION_VALID_FIELDS: dict[str, list[str]] = {
    "stop_reason": ["type", "value"],
    "output_contains": ["type", "value"],
    "output_not_contains": ["type", "value"],
    "output_matches_regex": ["type", "pattern"],
    "tool_called": ["type", "tool"],
    "tool_not_called": ["type", "tool"],
    "tool_called_times": ["type", "tool", "min", "max", "exactly"],
    "tool_args_match": ["type", "tool", "path", "pattern"],
    "tool_sequence": ["type", "tools"],
    "turn_count": ["type", "min", "max", "exactly"],
    "llm_judge": ["type", "criteria", "model"],
}

VALID_SUITE_FIELDS = {
    "suite",
    "skill",
    "defaults",
    "tools",
    "tests",
    "context",
    "conversation_prefix",
}
VALID_DEFAULTS_FIELDS = {
    "system_prompt",
    "model",
    "judge_model",
    "max_tokens",
    "temperature",
    "runs",
    "pass_threshold",
    "max_retries",
    "concurrency",
    "enable_caching",
}
VALID_SINGLE_TURN_FIELDS = {
    "type",
    "name",
    "input",
    "assertions",
    "runs",
    "pass_threshold",
    "baseline",
    "context",
}
VALID_MULTI_TURN_FIELDS = VALID_SINGLE_TURN_FIELDS | {"max_turns", "tool_responses"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _path(*parts) -> str:
    """Build a dotted path string from parts (strings and ints)."""
    result = []
    for p in parts:
        if isinstance(p, int):
            result.append(f"[{p}]")
        else:
            if result:
                result.append(".")
            result.append(str(p))
    return "".join(result)


def _suggest_typo(unknown: str, valid: list[str]) -> str | None:
    """Return the closest match from valid options if edit distance is small."""
    best, best_dist = None, float("inf")
    for candidate in valid:
        dist = _levenshtein(unknown.lower(), candidate.lower())
        if dist < best_dist:
            best, best_dist = candidate, dist
    if best_dist <= max(2, len(unknown) // 3):
        return best
    return None


def _levenshtein(a: str, b: str) -> int:
    """Simple Levenshtein distance."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if len(b) == 0:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[len(b)]


# ---------------------------------------------------------------------------
# Schema validation (replaces Pydantic)
# ---------------------------------------------------------------------------


def _validate_suite(raw: dict) -> list[str]:
    """Validate the top-level suite structure. Returns a list of error messages."""
    errors: list[str] = []

    # Required fields
    if "suite" not in raw:
        errors.append(
            'suite — missing required field\n  The top-level "suite" field names this eval suite.'
        )
    elif not isinstance(raw["suite"], str):
        errors.append(f"suite — wrong type\n  Expected string, got {type(raw['suite']).__name__}")

    if "skill" not in raw:
        errors.append(
            "skill — missing required field\n"
            '  The top-level "skill" field is a relative path to the SKILL.md being tested.'
        )
    elif not isinstance(raw["skill"], str):
        errors.append(f"skill — wrong type\n  Expected string, got {type(raw['skill']).__name__}")

    if "tests" not in raw:
        errors.append(
            "tests — missing required field\n"
            '  The "tests" field must be a list of test definitions.'
        )
    elif not isinstance(raw["tests"], list):
        errors.append(f"tests — wrong type\n  Expected list, got {type(raw['tests']).__name__}")

    # Unknown top-level fields
    for key in raw:
        if key not in VALID_SUITE_FIELDS:
            suggestion = _suggest_typo(key, list(VALID_SUITE_FIELDS))
            msg = f"{key} — unknown field"
            if suggestion:
                msg += f'\n  Did you mean "{suggestion}"?'
            errors.append(msg)

    # Validate defaults
    if "defaults" in raw:
        if not isinstance(raw["defaults"], dict):
            errors.append(
                f"defaults — wrong type\n  Expected mapping, got {type(raw['defaults']).__name__}"
            )
        else:
            errors.extend(_validate_defaults(raw["defaults"]))

    # Validate conversation_prefix
    if "conversation_prefix" in raw:
        errors.extend(_validate_conversation_prefix(raw["conversation_prefix"]))

    # Validate tests
    if isinstance(raw.get("tests"), list):
        for i, test in enumerate(raw["tests"]):
            if not isinstance(test, dict):
                errors.append(
                    f"{_path('tests', i)} — expected a mapping, got {type(test).__name__}"
                )
                continue
            errors.extend(_validate_test(test, i))

    return errors


def _validate_defaults(defaults: dict) -> list[str]:
    """Validate the defaults section."""
    errors: list[str] = []

    for key in defaults:
        if key not in VALID_DEFAULTS_FIELDS:
            suggestion = _suggest_typo(key, list(VALID_DEFAULTS_FIELDS))
            msg = f"defaults.{key} — unknown field"
            if suggestion:
                msg += f'\n  Did you mean "{suggestion}"?'
            errors.append(msg)

    runs = defaults.get("runs")
    if runs is not None:
        if not isinstance(runs, int):
            errors.append(
                f"defaults.runs — wrong type\n  Expected integer, got {type(runs).__name__}"
            )
        elif runs < 1:
            errors.append(f"defaults.runs — invalid value\n  runs must be >= 1, got {runs}")

    pt = defaults.get("pass_threshold")
    if pt is not None:
        if not isinstance(pt, (int, float)):
            errors.append(
                f"defaults.pass_threshold — wrong type\n  Expected number, got {type(pt).__name__}"
            )
        elif pt <= 0.0 or pt > 1.0:
            errors.append(
                "defaults.pass_threshold — invalid value\n"
                f"  pass_threshold must be in (0.0, 1.0], got {pt}"
            )

    conc = defaults.get("concurrency")
    if conc is not None:
        if not isinstance(conc, int):
            errors.append(
                f"defaults.concurrency — wrong type\n  Expected integer, got {type(conc).__name__}"
            )
        elif conc < 1:
            errors.append(
                f"defaults.concurrency — invalid value\n  concurrency must be >= 1, got {conc}"
            )

    mr = defaults.get("max_retries")
    if mr is not None:
        if not isinstance(mr, int):
            errors.append(
                f"defaults.max_retries — wrong type\n  Expected integer, got {type(mr).__name__}"
            )
        elif mr < 0:
            errors.append(
                f"defaults.max_retries — invalid value\n  max_retries must be >= 0, got {mr}"
            )

    return errors


def _validate_conversation_prefix(prefix) -> list[str]:
    """Validate the conversation_prefix section."""
    errors: list[str] = []
    base = "conversation_prefix"

    if not isinstance(prefix, dict):
        errors.append(f"{base} — wrong type\n  Expected mapping, got {type(prefix).__name__}")
        return errors

    has_messages = "messages" in prefix
    has_file = "file" in prefix

    if has_messages and has_file:
        errors.append(f'{base} — specify either "messages" or "file", not both')
    elif not has_messages and not has_file:
        errors.append(f'{base} — one of "messages" or "file" is required')

    if has_messages:
        msgs = prefix["messages"]
        if not isinstance(msgs, list):
            errors.append(
                f"{base}.messages — wrong type\n  Expected list, got {type(msgs).__name__}"
            )
        elif len(msgs) == 0:
            errors.append(f"{base}.messages — must not be empty")
        else:
            last = msgs[-1]
            if isinstance(last, dict) and last.get("role") != "assistant":
                errors.append(f"{base}.messages — must end with an assistant message")
            for i, msg in enumerate(msgs):
                errors.extend(_validate_message(msg, f"{base}.messages[{i}]"))

    if has_file and not isinstance(prefix["file"], str):
        errors.append(
            f"{base}.file — wrong type\n  Expected string, got {type(prefix['file']).__name__}"
        )

    return errors


def _validate_test(test: dict, idx: int) -> list[str]:
    """Validate a single test definition."""
    errors: list[str] = []
    test_name = test.get("name", f"at index {idx}")
    prefix = _path("tests", idx)

    # type field
    test_type = test.get("type")
    if test_type is None:
        errors.append(
            f"{prefix}.type — missing required field\n"
            f'  In test "{test_name}"\n'
            f'  Every test needs a "type" field.\n'
            f"  Valid types: {', '.join(VALID_TEST_TYPES)}"
        )
        return errors  # can't validate further without type

    if test_type not in VALID_TEST_TYPES:
        errors.append(
            f"{prefix} — invalid test type\n"
            f'  You wrote: type: "{test_type}"\n'
            f"  Valid types: {', '.join(VALID_TEST_TYPES)}\n"
            f'  Fix: Change to type: "single_turn" or type: "multi_turn"'
        )
        return errors

    # name field
    if "name" not in test:
        errors.append(
            f"{prefix}.name — missing required field\n"
            f'  Every test needs a "name" field describing what it checks.'
        )

    # input field
    if "input" not in test:
        errors.append(
            f"{prefix}.input — missing required field\n"
            f'  In test "{test_name}"\n'
            f'  Every test needs an "input" with a "messages" list.\n'
            f"  Example:\n"
            f"    input:\n"
            f"      messages:\n"
            f"        - role: user\n"
            f'          content: "Your prompt here"'
        )
    elif not isinstance(test["input"], dict):
        errors.append(
            f"{prefix}.input — wrong type\n  Expected mapping, got {type(test['input']).__name__}"
        )
    else:
        errors.extend(_validate_input(test["input"], prefix))

    # assertions field
    if "assertions" not in test:
        errors.append(
            f"{prefix}.assertions — missing required field\n"
            f'  In test "{test_name}"\n'
            f'  Every test needs an "assertions" list (can be empty).\n'
            f"  Example:\n"
            f"    assertions:\n"
            f"      - type: output_contains\n"
            f'        value: "expected text"'
        )
    elif not isinstance(test["assertions"], list):
        errors.append(
            f"{prefix}.assertions — wrong type\n"
            f"  Expected list, got {type(test['assertions']).__name__}"
        )
    else:
        for j, assertion in enumerate(test["assertions"]):
            if not isinstance(assertion, dict):
                errors.append(
                    f"{prefix}.assertions[{j}] — expected a mapping, got {type(assertion).__name__}"
                )
                continue
            errors.extend(_validate_assertion(assertion, prefix, j))

    # tool_responses (multi_turn only)
    if "tool_responses" in test:
        if not isinstance(test["tool_responses"], list):
            errors.append(
                f"{prefix}.tool_responses — wrong type\n"
                f"  Expected list, got {type(test['tool_responses']).__name__}"
            )
        else:
            for k, tr in enumerate(test["tool_responses"]):
                if isinstance(tr, dict):
                    errors.extend(_validate_tool_response(tr, f"{prefix}.tool_responses[{k}]"))

    # Unknown fields
    valid_fields = (
        VALID_MULTI_TURN_FIELDS if test_type == "multi_turn" else VALID_SINGLE_TURN_FIELDS
    )
    for key in test:
        if key not in valid_fields:
            suggestion = _suggest_typo(key, list(valid_fields))
            msg = f'{prefix}.{key} — unknown field "{key}"'
            if suggestion:
                msg += f'\n  Did you mean "{suggestion}"?'
            errors.append(msg)

    return errors


def _validate_input(inp: dict, prefix: str) -> list[str]:
    """Validate an input section."""
    errors: list[str] = []
    if "messages" not in inp:
        errors.append(
            f"{prefix}.input.messages — missing required field\n"
            f'  The "input" field requires a "messages" list.\n'
            f"  Example:\n"
            f"    input:\n"
            f"      messages:\n"
            f"        - role: user\n"
            f'          content: "Your prompt here"'
        )
    elif not isinstance(inp["messages"], list):
        errors.append(
            f"{prefix}.input.messages — wrong type\n"
            f"  Expected list, got {type(inp['messages']).__name__}"
        )
    else:
        for i, msg in enumerate(inp["messages"]):
            errors.extend(_validate_message(msg, f"{prefix}.input.messages[{i}]"))
    return errors


def _validate_message(msg, path: str) -> list[str]:
    """Validate a single message."""
    errors: list[str] = []
    if not isinstance(msg, dict):
        errors.append(f"{path} — expected a mapping, got {type(msg).__name__}")
        return errors

    role = msg.get("role")
    if role is None:
        errors.append(
            f"{path}.role — missing required field\n"
            f'  Messages need a "role" field. Valid roles: {", ".join(VALID_MESSAGE_ROLES)}'
        )
    elif role not in VALID_MESSAGE_ROLES:
        errors.append(
            f"{path} — invalid message role\n"
            f'  You wrote: role: "{role}"\n'
            f"  Valid roles: {', '.join(VALID_MESSAGE_ROLES)}"
        )

    return errors


def _validate_assertion(assertion: dict, test_prefix: str, idx: int) -> list[str]:
    """Validate a single assertion."""
    errors: list[str] = []
    path = f"{test_prefix}.assertions[{idx}]"

    atype = assertion.get("type")
    if atype is None:
        errors.append(
            f"{path}.type — missing required field\n"
            f'  Every assertion needs a "type" field.\n'
            f"  Valid types: {', '.join(VALID_ASSERTION_TYPES)}"
        )
        return errors

    if atype not in VALID_ASSERTION_TYPES:
        errors.append(
            f"{path} — unknown assertion type\n"
            f'  You wrote: type: "{atype}"\n'
            f"  Valid types: {', '.join(VALID_ASSERTION_TYPES)}\n"
            f"  Fix: Use one of the valid assertion types listed above."
        )
        return errors

    # Check required fields for this assertion type
    for field, expected_type in ASSERTION_REQUIRED_FIELDS[atype]:
        if field not in assertion:
            errors.append(f'{path}.{field} — missing required field for "{atype}" assertion')
        elif not isinstance(assertion[field], expected_type):
            errors.append(
                f"{path}.{field} — wrong type\n"
                f"  Expected {expected_type.__name__}, got {type(assertion[field]).__name__}"
            )

    # Validate regex pattern
    if (
        atype == "output_matches_regex"
        and "pattern" in assertion
        and isinstance(assertion["pattern"], str)
    ):
        try:
            re.compile(assertion["pattern"])
        except re.error as e:
            errors.append(f"{path}.pattern — invalid regex pattern\n  {e}")

    # Check for unknown fields
    valid = ASSERTION_VALID_FIELDS.get(atype, [])
    for key in assertion:
        if key not in valid:
            suggestion = _suggest_typo(key, valid)
            msg = f'{path}.{key} — unknown field "{key}" for "{atype}" assertion'
            if suggestion:
                msg += f'\n  Did you mean "{suggestion}"?'
            errors.append(msg)

    return errors


def _validate_tool_response(tr: dict, path: str) -> list[str]:
    """Validate a single tool_response entry."""
    errors: list[str] = []

    if "match" not in tr:
        errors.append(f"{path}.match — missing required field")

    has_response = "response" in tr
    has_responses = "responses" in tr

    if has_response and has_responses:
        errors.append(f'{path} — specify either "response" or "responses", not both')
    elif not has_response and not has_responses:
        errors.append(f'{path} — one of "response" or "responses" is required')

    if has_responses:
        if not isinstance(tr["responses"], list):
            errors.append(
                f"{path}.responses — wrong type\n"
                f"  Expected list, got {type(tr['responses']).__name__}"
            )
        elif len(tr["responses"]) == 0:
            errors.append(f"{path}.responses — must not be empty")

    return errors


# ---------------------------------------------------------------------------
# Semantic checks (beyond schema validation)
# ---------------------------------------------------------------------------


def _run_semantic_checks(raw: dict) -> list[str]:
    """Run additional semantic checks that catch common LLM mistakes."""
    warnings: list[str] = []
    tests = raw.get("tests", [])
    declared_tools = _get_declared_tool_names(raw)

    for i, test in enumerate(tests):
        if not isinstance(test, dict):
            continue
        test_name = test.get("name", f"at index {i}")
        test_type = test.get("type")

        # tool_result without matching tool_use_id
        _check_tool_result_ids(test, i, test_name, warnings)

        # Tool assertions referencing undeclared tools
        if declared_tools is not None:
            _check_undeclared_tools(test, i, test_name, declared_tools, warnings)

        # multi_turn without tool_responses
        if test_type == "multi_turn" and not test.get("tool_responses"):
            warnings.append(
                f'tests[{i}] "{test_name}" — multi_turn test with no tool_responses\n'
                f"  A multi_turn test needs tool_responses to script how tools reply.\n"
                f'  If you don\'t need tool interaction, use type: "single_turn" instead.'
            )

        # llm_judge criteria too short
        for j, assertion in enumerate(test.get("assertions", [])):
            if not isinstance(assertion, dict):
                continue
            if assertion.get("type") == "llm_judge":
                criteria = assertion.get("criteria", "")
                if isinstance(criteria, str) and len(criteria) < 10:
                    warnings.append(
                        f'tests[{i}].assertions[{j}] "{test_name}" — '
                        f"llm_judge criteria is very short ({len(criteria)} chars)\n"
                        f'  You wrote: "{criteria}"\n'
                        f"  Criteria should be a detailed description of "
                        f"what to evaluate (at least a sentence)."
                    )

        # skill_only checks
        _check_skill_only(test, i, test_name, warnings)

    return warnings


def _get_declared_tool_names(raw: dict) -> list[str] | None:
    """Extract tool names from suite-level tools declaration. Returns None if no tools declared."""
    tools = raw.get("tools")
    if tools is None:
        return None
    names = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if "builtin" in tool:
            names.append(tool["builtin"])
        elif "name" in tool:
            names.append(tool["name"])
    return names


def _check_tool_result_ids(test: dict, idx: int, name: str, warnings: list[str]) -> None:
    """Check that tool_result messages reference a tool_call id from a prior assistant message."""
    messages = test.get("input", {}).get("messages", [])
    known_ids: set[str] = set()

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role == "assistant":
            for tc in msg.get("tool_calls", []):
                if isinstance(tc, dict):
                    tc_id = tc.get("id")
                    if tc_id:
                        known_ids.add(tc_id)
        elif role == "tool_result":
            tool_use_id = msg.get("tool_use_id")
            if tool_use_id and tool_use_id not in known_ids:
                warnings.append(
                    f'tests[{idx}] "{name}" — tool_result references '
                    f'unknown tool_use_id "{tool_use_id}"\n'
                    f'  No prior assistant message has a tool_call with id: "{tool_use_id}".\n'
                    f"  Add a matching tool_call in the assistant message before this tool_result."
                )


def _check_undeclared_tools(
    test: dict, idx: int, name: str, declared: list[str], warnings: list[str]
) -> None:
    """Check that tool assertions reference tools declared in the suite's tools list."""
    for j, assertion in enumerate(test.get("assertions", [])):
        if not isinstance(assertion, dict):
            continue
        atype = assertion.get("type")
        # tool_called, tool_not_called, tool_called_times, tool_args_match
        if atype in ("tool_called", "tool_not_called", "tool_called_times", "tool_args_match"):
            tool = assertion.get("tool")
            if tool and tool not in declared:
                warnings.append(
                    f'tests[{idx}].assertions[{j}] "{name}" — references tool "{tool}" '
                    f"not declared in suite tools\n"
                    f"  Declared tools: {', '.join(declared)}\n"
                    f'  Either add "{tool}" to the top-level tools list or fix the assertion.'
                )
        # tool_sequence
        if atype == "tool_sequence":
            for tool_name in assertion.get("tools", []):
                if tool_name not in declared:
                    warnings.append(
                        f'tests[{idx}].assertions[{j}] "{name}" — tool_sequence references '
                        f'"{tool_name}" not declared in suite tools\n'
                        f"  Declared tools: {', '.join(declared)}\n"
                        f'  Either add "{tool_name}" to the top-level '
                        f"tools list or fix the assertion."
                    )
                    break  # one warning per assertion is enough


def _check_skill_only(test: dict, idx: int, name: str, warnings: list[str]) -> None:
    """Check skill_only consistency: orphaned pairs and missing baseline."""
    messages = test.get("input", {}).get("messages", [])
    has_skill_only = False

    # Build maps: tool_call id → assistant msg index, tool_result tool_use_id → msg index
    tc_id_to_msg: dict[str, int] = {}  # tool_call id → message index of assistant
    tr_id_to_msg: dict[str, int] = {}  # tool_use_id → message index of tool_result

    for mi, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue
        if msg.get("skill_only"):
            has_skill_only = True
        role = msg.get("role")
        if role == "assistant":
            for tc in msg.get("tool_calls", []):
                if isinstance(tc, dict) and tc.get("id"):
                    tc_id_to_msg[tc["id"]] = mi
        elif role == "tool_result":
            tuid = msg.get("tool_use_id")
            if tuid:
                tr_id_to_msg[tuid] = mi

    # Check orphaned skill_only pairs
    for mi, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        is_skill_only = bool(msg.get("skill_only"))

        if role == "tool_result" and is_skill_only:
            tuid = msg.get("tool_use_id")
            if tuid and tuid in tc_id_to_msg:
                asst_idx = tc_id_to_msg[tuid]
                asst_msg = messages[asst_idx]
                if isinstance(asst_msg, dict) and not asst_msg.get("skill_only"):
                    warnings.append(
                        f'tests[{idx}] "{name}" — orphaned skill_only pair\n'
                        f"  input.messages[{mi}] (tool_result, "
                        f'tool_use_id="{tuid}") is skill_only: true\n'
                        f"  but the matching assistant message at index {asst_idx} is not.\n"
                        f"  Baseline would have the tool_call but no result. "
                        f"Mark both as skill_only: true."
                    )

        if role == "assistant" and is_skill_only:
            for tc in msg.get("tool_calls", []):
                if not isinstance(tc, dict):
                    continue
                tc_id = tc.get("id")
                if tc_id and tc_id in tr_id_to_msg:
                    tr_idx = tr_id_to_msg[tc_id]
                    tr_msg = messages[tr_idx]
                    if isinstance(tr_msg, dict) and not tr_msg.get("skill_only"):
                        warnings.append(
                            f'tests[{idx}] "{name}" — orphaned skill_only pair\n'
                            f"  input.messages[{mi}] (assistant with "
                            f'tool_call id="{tc_id}") is skill_only: true\n'
                            f"  but the matching tool_result at index {tr_idx} is not.\n"
                            f"  Baseline would have the result but no call. "
                            f"Mark both as skill_only: true."
                        )

    # skill_only without baseline
    if has_skill_only and not test.get("baseline"):
        warnings.append(
            f'tests[{idx}] "{name}" — skill_only messages without baseline\n'
            f"  Messages are marked skill_only: true but baseline: false (or omitted).\n"
            f"  skill_only has no effect without baseline enabled."
        )


# ---------------------------------------------------------------------------
# Summary on success
# ---------------------------------------------------------------------------


def _format_success(raw: dict) -> str:
    """Format a success message with suite summary."""
    tests = raw.get("tests", [])
    total_tests = len(tests)
    total_assertions = sum(len(t.get("assertions", [])) for t in tests if isinstance(t, dict))

    type_counts: Counter = Counter()
    for test in tests:
        if not isinstance(test, dict):
            continue
        for a in test.get("assertions", []):
            if isinstance(a, dict) and "type" in a:
                type_counts[a["type"]] += 1

    suite_name = raw.get("suite", "unnamed")
    lines = [
        f'VALIDATION PASSED: suite "{suite_name}" '
        f"({total_tests} tests, {total_assertions} assertions)"
    ]

    if type_counts:
        lines.append("")
        lines.append("Assertion distribution:")
        for atype, count in type_counts.most_common():
            lines.append(f"  {atype}: {count}")

    test_type_counts: Counter = Counter()
    for t in tests:
        if isinstance(t, dict) and "type" in t:
            test_type_counts[t["type"]] += 1
    lines.append("")
    lines.append("Test types:")
    for ttype, count in test_type_counts.most_common():
        lines.append(f"  {ttype}: {count}")

    baseline_count = sum(1 for t in tests if isinstance(t, dict) and t.get("baseline"))
    if baseline_count:
        lines.append(f"\nBaseline tests: {baseline_count}/{total_tests}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------


def validate_eval_file(path: str | Path) -> tuple[bool, str]:
    """Validate an eval YAML file and return (success, message).

    Returns:
        (True, success_summary) if valid
        (False, error_report) if invalid
    """
    path = Path(path)

    if not path.exists():
        return False, f"VALIDATION FAILED: File not found: {path}"

    # Step 1: Parse YAML
    try:
        text = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return False, f"VALIDATION FAILED: Invalid YAML syntax\n\n  {e}"

    if not isinstance(raw, dict):
        return False, "VALIDATION FAILED: Expected a YAML mapping at the top level"

    # Step 2: Schema validation
    errors = _validate_suite(raw)
    if errors:
        total = len(errors)
        lines = [f"VALIDATION FAILED: {total} error{'s' if total != 1 else ''} found"]
        for i, err_msg in enumerate(errors, 1):
            lines.append(f"\nError {i}/{total}: {err_msg}")
        return False, "\n".join(lines)

    # Step 3: Semantic checks
    warnings = _run_semantic_checks(raw)
    if warnings:
        total = len(warnings)
        lines = [_format_success(raw)]
        lines.append(f"\n--- {total} warning{'s' if total != 1 else ''} ---")
        for i, warn in enumerate(warnings, 1):
            lines.append(f"\nWarning {i}/{total}: {warn}")
        return True, "\n".join(lines)

    return True, _format_success(raw)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python validate_eval.py <path-to-eval.yaml>", file=sys.stderr)
        sys.exit(2)

    path = sys.argv[1]
    success, message = validate_eval_file(path)
    print(message)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
