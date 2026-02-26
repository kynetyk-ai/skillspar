"""Cost estimation for Claude API usage."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from skill_evaluator.engine.trace import TokenUsage

logger = logging.getLogger(__name__)

# Pricing per million tokens (USD).
# Format: model_id -> {input, output, cache_write_multiplier, cache_read_multiplier}
# cache_write cost = input * cache_write_multiplier
# cache_read cost  = input * cache_read_multiplier
_BUILTIN_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-5-20250929": {
        "input": 3.00,
        "output": 15.00,
        "cache_write_multiplier": 1.25,
        "cache_read_multiplier": 0.1,
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.80,
        "output": 4.00,
        "cache_write_multiplier": 1.25,
        "cache_read_multiplier": 0.1,
    },
    "claude-opus-4-20250514": {
        "input": 15.00,
        "output": 75.00,
        "cache_write_multiplier": 1.25,
        "cache_read_multiplier": 0.1,
    },
}


def _load_pricing() -> dict[str, dict[str, float]]:
    """Load pricing table, optionally extended/overridden by env var."""
    pricing = dict(_BUILTIN_PRICING)
    pricing_file = os.environ.get("SKILLSPAR_PRICING_FILE")
    if pricing_file:
        try:
            with open(pricing_file) as f:
                custom = json.load(f)
            if isinstance(custom, dict):
                pricing.update(custom)
                logger.debug("Loaded custom pricing from %s (%d models)", pricing_file, len(custom))
            else:
                logger.warning("SKILLSPAR_PRICING_FILE contents must be a JSON object, ignoring")
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to load SKILLSPAR_PRICING_FILE (%s): %s", pricing_file, e)
    return pricing


def estimate_cost(usage: TokenUsage, model: str) -> float | None:
    """Estimate cost in USD for a single API usage record.

    Returns None if the model is not in the pricing table.
    """
    pricing = _load_pricing()
    model_pricing = pricing.get(model)
    if model_pricing is None:
        logger.warning("No pricing data for model '%s'; cost will be null", model)
        return None

    per_m_input = model_pricing["input"]
    per_m_output = model_pricing["output"]
    cache_write_mult = model_pricing.get("cache_write_multiplier", 1.25)
    cache_read_mult = model_pricing.get("cache_read_multiplier", 0.1)

    cost = 0.0
    # Standard input tokens (non-cache)
    cost += usage.input_tokens * per_m_input / 1_000_000
    # Output tokens
    cost += usage.output_tokens * per_m_output / 1_000_000
    # Cache write tokens
    if usage.cache_creation_input_tokens:
        cost += usage.cache_creation_input_tokens * per_m_input * cache_write_mult / 1_000_000
    # Cache read tokens
    if usage.cache_read_input_tokens:
        cost += usage.cache_read_input_tokens * per_m_input * cache_read_mult / 1_000_000

    return cost


def estimate_cache_savings(cache_read_tokens: int, model: str) -> float | None:
    """Estimate savings from cache reads vs. full-price input tokens.

    Savings = cache_read_tokens * input_rate * (1 - cache_read_multiplier) / 1M
    """
    pricing = _load_pricing()
    model_pricing = pricing.get(model)
    if model_pricing is None:
        return None
    per_m_input = model_pricing["input"]
    cache_read_mult = model_pricing.get("cache_read_multiplier", 0.1)
    return cache_read_tokens * per_m_input * (1.0 - cache_read_mult) / 1_000_000


def build_cache_summary(
    suite_result: Any,
    model: str,
) -> dict[str, Any] | None:
    """Build cache summary dict from a SuiteResult.

    Returns None if no cache data is present.
    """
    total_cache_creation = 0
    total_cache_read = 0
    has_cache = False
    for group in suite_result.test_results:
        all_runs = list(group.runs) + (group.baseline_runs or [])
        for r in all_runs:
            if r.trace:
                u = r.trace.total_usage
                if u.cache_creation_input_tokens is not None:
                    total_cache_creation += u.cache_creation_input_tokens
                    has_cache = True
                if u.cache_read_input_tokens is not None:
                    total_cache_read += u.cache_read_input_tokens
                    has_cache = True
    if not has_cache:
        return None
    savings = estimate_cache_savings(total_cache_read, model)
    return {
        "cache_creation_input_tokens": total_cache_creation,
        "cache_read_input_tokens": total_cache_read,
        "estimated_savings_usd": round(savings, 6) if savings is not None else None,
    }


def build_cost_summary(
    suite_result: Any,
    model: str,
) -> dict[str, Any] | None:
    """Build cost summary dict from a SuiteResult.

    Returns None if cost cannot be estimated for the model.
    """
    from skill_evaluator.engine.trace import TokenUsage

    skill_input = 0
    skill_output = 0
    skill_cache_creation = 0
    skill_cache_read = 0
    baseline_input = 0
    baseline_output = 0
    baseline_cache_creation = 0
    baseline_cache_read = 0

    for group in suite_result.test_results:
        for run in group.runs:
            if run.trace:
                u = run.trace.total_usage
                skill_input += u.input_tokens
                skill_output += u.output_tokens
                skill_cache_creation += u.cache_creation_input_tokens or 0
                skill_cache_read += u.cache_read_input_tokens or 0
        if group.baseline_runs:
            for run in group.baseline_runs:
                if run.trace:
                    u = run.trace.total_usage
                    baseline_input += u.input_tokens
                    baseline_output += u.output_tokens
                    baseline_cache_creation += u.cache_creation_input_tokens or 0
                    baseline_cache_read += u.cache_read_input_tokens or 0

    skill_usage = TokenUsage(
        input_tokens=skill_input,
        output_tokens=skill_output,
        cache_creation_input_tokens=skill_cache_creation or None,
        cache_read_input_tokens=skill_cache_read or None,
    )
    baseline_usage = TokenUsage(
        input_tokens=baseline_input,
        output_tokens=baseline_output,
        cache_creation_input_tokens=baseline_cache_creation or None,
        cache_read_input_tokens=baseline_cache_read or None,
    )

    skill_cost = estimate_cost(skill_usage, model)
    baseline_cost = estimate_cost(baseline_usage, model)

    if skill_cost is None:
        return None

    total_cost = skill_cost + (baseline_cost or 0.0)

    result: dict[str, Any] = {
        "total_cost_usd": round(total_cost, 6),
        "skill_cost_usd": round(skill_cost, 6),
    }
    if baseline_cost is not None and baseline_cost > 0:
        result["baseline_cost_usd"] = round(baseline_cost, 6)

    return result
