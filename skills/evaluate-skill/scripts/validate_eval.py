#!/usr/bin/env python3
"""Validate a .eval.yaml file and produce LLM-friendly error messages.

Usage:
    python validate_eval.py <path-to-eval-yaml>

Runs Pydantic schema validation and additional semantic checks, translating
cryptic errors into actionable fix instructions.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

import yaml
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Ensure the project root is importable when run as a standalone script
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[2]  # skills/evaluate-skill/scripts -> repo root
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from skill_evaluator.config.schema import EvalSuite  # noqa: E402

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

# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------


def _humanize_loc(loc: tuple) -> str:
    """Convert a Pydantic error location tuple to a dotted path string."""
    parts = []
    for item in loc:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        else:
            if parts:
                parts.append(".")
            parts.append(str(item))
    return "".join(parts)


def _find_value_at_loc(raw: dict, loc: tuple):
    """Walk into raw YAML dict following a Pydantic loc path."""
    current = raw
    for key in loc:
        try:
            if isinstance(current, dict):
                current = current[key]
            elif isinstance(current, list) and isinstance(key, int):
                current = current[key]
            else:
                return None
        except (KeyError, IndexError, TypeError):
            return None
    return current


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


def translate_pydantic_errors(exc: ValidationError, raw: dict) -> list[str]:
    """Translate a Pydantic ValidationError into LLM-friendly messages."""
    messages = []
    for error in exc.errors():
        loc = error["loc"]
        err_type = error["type"]
        msg = error["msg"]
        path = _humanize_loc(loc)
        actual_value = _find_value_at_loc(raw, loc)

        translated = _translate_single_error(loc, err_type, msg, path, actual_value, raw)
        messages.append(translated)
    return messages


def _translate_single_error(
    loc: tuple,
    err_type: str,
    msg: str,
    path: str,
    actual_value,
    raw: dict,
) -> str:
    """Translate one Pydantic error into a human-friendly message."""

    # --- Discriminator errors (wrong type on tests or assertions) ---
    if err_type == "union_tag_invalid":
        # Extract the actual 'type' value from the dict if needed
        disc_value = actual_value
        if isinstance(disc_value, dict):
            disc_value = disc_value.get("type", disc_value)
        # Determine if this is a test type or assertion type discriminator
        if _loc_contains(loc, "assertions"):
            return (
                f"{path} — unknown assertion type\n"
                f"  You wrote: type: \"{disc_value}\"\n"
                f"  Valid types: {', '.join(VALID_ASSERTION_TYPES)}\n"
                f"  Fix: Use one of the valid assertion types listed above."
            )
        if _loc_contains(loc, "tests"):
            return (
                f"{path} — invalid test type\n"
                f"  You wrote: type: \"{disc_value}\"\n"
                f"  Valid types: {', '.join(VALID_TEST_TYPES)}\n"
                f"  Fix: Change to type: \"single_turn\" or type: \"multi_turn\""
            )
        return f"{path} — invalid discriminator value: {disc_value}\n  {msg}"

    # --- Missing required fields ---
    if err_type == "missing":
        field_name = loc[-1] if loc else "unknown"
        context = _describe_location(loc, raw)
        hint = _missing_field_hint(field_name, loc)
        result = f"{path} — missing required field\n  {context}"
        if hint:
            result += f"\n  {hint}"
        return result

    # --- Extra/unknown fields ---
    if err_type == "extra_forbidden":
        field_name = str(loc[-1]) if loc else "unknown"
        # Try to suggest a correction
        parent_loc = loc[:-1]
        valid_fields = _get_valid_fields_for_loc(parent_loc, raw)
        suggestion = _suggest_typo(field_name, valid_fields) if valid_fields else None
        result = f"{path} — unknown field \"{field_name}\""
        if suggestion:
            result += f"\n  Did you mean \"{suggestion}\"?"
        return result

    # --- Type errors ---
    if err_type in ("string_type", "int_type", "float_type", "bool_type", "list_type", "dict_type"):
        expected = err_type.replace("_type", "")
        got = type(actual_value).__name__ if actual_value is not None else "null"
        return f"{path} — wrong type\n  Expected {expected}, got {got}"

    # --- Value errors (validators) ---
    if err_type == "value_error":
        return f"{path} — invalid value\n  {msg}"

    # --- Regex pattern errors ---
    if "regex" in str(msg).lower() or "pattern" in str(msg).lower():
        return f"{path} — invalid regex pattern\n  {msg}"

    # --- Literal errors (e.g., role must be user/assistant/tool_result) ---
    if err_type == "literal_error":
        if _loc_ends_with(loc, "role"):
            return (
                f"{path} — invalid message role\n"
                f"  You wrote: role: \"{actual_value}\"\n"
                f"  Valid roles: {', '.join(VALID_MESSAGE_ROLES)}"
            )
        return f"{path} — invalid value\n  {msg}"

    # --- Fallback: just clean up the Pydantic message ---
    return f"{path} — {msg}"


def _loc_contains(loc: tuple, key: str) -> bool:
    return any(str(item) == key for item in loc)


def _loc_ends_with(loc: tuple, key: str) -> bool:
    return len(loc) > 0 and str(loc[-1]) == key


def _describe_location(loc: tuple, raw: dict) -> str:
    """Describe where in the YAML structure this error occurred."""
    for i, part in enumerate(loc):
        if part == "tests" and i + 1 < len(loc) and isinstance(loc[i + 1], int):
            idx = loc[i + 1]
            tests = raw.get("tests", [])
            name = tests[idx].get("name", f"at index {idx}") if idx < len(tests) else f"at index {idx}"
            return f"In test \"{name}\""
    return ""


def _missing_field_hint(field_name, loc: tuple) -> str | None:
    """Provide a helpful hint for commonly missing fields."""
    hints = {
        "input": (
            "Every test needs an \"input\" with a \"messages\" list.\n"
            "  Example:\n"
            "    input:\n"
            "      messages:\n"
            "        - role: user\n"
            "          content: \"Your prompt here\""
        ),
        "messages": (
            "The \"input\" field requires a \"messages\" list.\n"
            "  Example:\n"
            "    input:\n"
            "      messages:\n"
            "        - role: user\n"
            "          content: \"Your prompt here\""
        ),
        "assertions": (
            "Every test needs an \"assertions\" list (can be empty).\n"
            "  Example:\n"
            "    assertions:\n"
            "      - type: output_contains\n"
            "        value: \"expected text\""
        ),
        "name": "Every test needs a \"name\" field describing what it checks.",
        "suite": "The top-level \"suite\" field names this eval suite.",
        "skill": "The top-level \"skill\" field is a relative path to the SKILL.md being tested.",
        "type": (
            f"Every test needs a \"type\" field.\n"
            f"  Valid types: {', '.join(VALID_TEST_TYPES)}"
        ),
        "content": "Messages need a \"content\" field with the text.",
        "role": f"Messages need a \"role\" field. Valid roles: {', '.join(VALID_MESSAGE_ROLES)}",
    }
    return hints.get(str(field_name))


def _get_valid_fields_for_loc(parent_loc: tuple, raw: dict) -> list[str] | None:
    """Get valid field names for the object at the given location."""
    # Walk up to figure out what kind of object this is
    parent = _find_value_at_loc(raw, parent_loc)
    if not isinstance(parent, dict):
        return None

    test_type = parent.get("type")
    if test_type in ("single_turn", "multi_turn"):
        base = ["type", "name", "input", "assertions", "runs", "pass_threshold", "baseline", "context"]
        if test_type == "multi_turn":
            base.extend(["max_turns", "tool_responses"])
        return base

    # Check if it's an assertion
    if "type" in parent and parent.get("type") in VALID_ASSERTION_TYPES:
        return ["type", "value", "pattern", "tool", "tools", "path", "min", "max", "exactly", "criteria", "model"]

    # Top-level suite
    if "suite" in parent or "tests" in parent:
        return ["suite", "skill", "defaults", "tools", "tests", "context", "conversation_prefix"]

    return None


# ---------------------------------------------------------------------------
# Semantic checks (beyond Pydantic schema validation)
# ---------------------------------------------------------------------------


def run_semantic_checks(raw: dict, suite: EvalSuite) -> list[str]:
    """Run additional semantic checks that catch common LLM mistakes."""
    warnings = []
    tests = raw.get("tests", [])
    declared_tools = _get_declared_tool_names(suite)

    for i, test_raw in enumerate(tests):
        test_name = test_raw.get("name", f"at index {i}")
        test_type = test_raw.get("type")
        test_obj = suite.tests[i]

        # tool_result without matching tool_use_id
        _check_tool_result_ids(test_raw, i, test_name, warnings)

        # Tool assertions referencing undeclared tools
        if declared_tools is not None:
            _check_undeclared_tools(test_obj, i, test_name, declared_tools, warnings)

        # multi_turn without tool_responses
        if test_type == "multi_turn" and not test_raw.get("tool_responses"):
            warnings.append(
                f"tests[{i}] \"{test_name}\" — multi_turn test with no tool_responses\n"
                f"  A multi_turn test needs tool_responses to script how tools reply.\n"
                f"  If you don't need tool interaction, use type: \"single_turn\" instead."
            )

        # llm_judge criteria too short
        for j, assertion in enumerate(test_obj.assertions):
            if hasattr(assertion, "criteria") and len(assertion.criteria) < 10:
                warnings.append(
                    f"tests[{i}].assertions[{j}] \"{test_name}\" — llm_judge criteria is very short "
                    f"({len(assertion.criteria)} chars)\n"
                    f"  You wrote: \"{assertion.criteria}\"\n"
                    f"  Criteria should be a detailed description of what to evaluate (at least a sentence)."
                )

    return warnings


def _get_declared_tool_names(suite: EvalSuite) -> list[str] | None:
    """Extract tool names from suite-level tools declaration. Returns None if no tools declared."""
    if suite.tools is None:
        return None
    names = []
    for tool in suite.tools:
        if hasattr(tool, "builtin"):
            names.append(tool.builtin)
        elif hasattr(tool, "name"):
            names.append(tool.name)
    return names


def _check_tool_result_ids(test_raw: dict, idx: int, name: str, warnings: list[str]) -> None:
    """Check that tool_result messages reference a tool_call id from a prior assistant message."""
    messages = test_raw.get("input", {}).get("messages", [])
    known_tool_call_ids: set[str] = set()

    for msg in messages:
        role = msg.get("role")
        if role == "assistant":
            for tc in msg.get("tool_calls", []):
                tc_id = tc.get("id")
                if tc_id:
                    known_tool_call_ids.add(tc_id)
        elif role == "tool_result":
            tool_use_id = msg.get("tool_use_id")
            if tool_use_id and tool_use_id not in known_tool_call_ids:
                warnings.append(
                    f"tests[{idx}] \"{name}\" — tool_result references unknown tool_use_id \"{tool_use_id}\"\n"
                    f"  No prior assistant message has a tool_call with id: \"{tool_use_id}\".\n"
                    f"  Add a matching tool_call in the assistant message before this tool_result."
                )


def _check_undeclared_tools(test_obj, idx: int, name: str, declared: list[str], warnings: list[str]) -> None:
    """Check that tool assertions reference tools declared in the suite's tools list."""
    for j, assertion in enumerate(test_obj.assertions):
        # tool_called, tool_not_called, tool_called_times, tool_args_match
        if hasattr(assertion, "tool") and assertion.tool not in declared:
            warnings.append(
                f"tests[{idx}].assertions[{j}] \"{name}\" — references tool \"{assertion.tool}\" "
                f"not declared in suite tools\n"
                f"  Declared tools: {', '.join(declared)}\n"
                f"  Either add \"{assertion.tool}\" to the top-level tools list or fix the assertion."
            )
        # tool_sequence
        if hasattr(assertion, "tools"):
            for tool_name in assertion.tools:
                if tool_name not in declared:
                    warnings.append(
                        f"tests[{idx}].assertions[{j}] \"{name}\" — tool_sequence references "
                        f"\"{tool_name}\" not declared in suite tools\n"
                        f"  Declared tools: {', '.join(declared)}\n"
                        f"  Either add \"{tool_name}\" to the top-level tools list or fix the assertion."
                    )
                    break  # one warning per assertion is enough


# ---------------------------------------------------------------------------
# Summary on success
# ---------------------------------------------------------------------------


def format_success(suite: EvalSuite) -> str:
    """Format a success message with suite summary."""
    total_tests = len(suite.tests)
    total_assertions = sum(len(t.assertions) for t in suite.tests)

    type_counts = Counter()
    for test in suite.tests:
        for a in test.assertions:
            type_counts[a.type] += 1

    lines = [f"VALIDATION PASSED: suite \"{suite.suite}\" ({total_tests} tests, {total_assertions} assertions)"]

    if type_counts:
        lines.append("")
        lines.append("Assertion distribution:")
        for atype, count in type_counts.most_common():
            lines.append(f"  {atype}: {count}")

    test_type_counts = Counter(t.type for t in suite.tests)
    lines.append("")
    lines.append("Test types:")
    for ttype, count in test_type_counts.most_common():
        lines.append(f"  {ttype}: {count}")

    baseline_count = sum(1 for t in suite.tests if t.baseline)
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

    # Step 2: Inject env defaults (same as the real loader)
    defaults = raw.setdefault("defaults", {})
    env_model = os.environ.get("SKILLSPAR_MODEL")
    if env_model and "model" not in defaults:
        defaults["model"] = env_model
    env_judge = os.environ.get("SKILLSPAR_JUDGE_MODEL")
    if env_judge and "judge_model" not in defaults:
        defaults["judge_model"] = env_judge

    # Step 3: Pydantic schema validation
    try:
        suite = EvalSuite.model_validate(raw)
    except ValidationError as e:
        errors = translate_pydantic_errors(e, raw)
        total = len(errors)
        lines = [f"VALIDATION FAILED: {total} error{'s' if total != 1 else ''} found"]
        for i, err_msg in enumerate(errors, 1):
            lines.append(f"\nError {i}/{total}: {err_msg}")
        return False, "\n".join(lines)

    # Step 4: Semantic checks
    warnings = run_semantic_checks(raw, suite)
    if warnings:
        total = len(warnings)
        lines = [format_success(suite)]
        lines.append(f"\n--- {total} warning{'s' if total != 1 else ''} ---")
        for i, warn in enumerate(warnings, 1):
            lines.append(f"\nWarning {i}/{total}: {warn}")
        return True, "\n".join(lines)

    return True, format_success(suite)


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
