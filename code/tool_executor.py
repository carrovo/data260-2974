import json
import logging
from typing import Any, Callable

from domain_tools import error_response
from reliable_domain_tools import (
    listing_details,
    manager_rent_summary,
    search_listings,
)


logger = logging.getLogger("s2974_rel.tool_executor")

Envelope = dict[str, Any]
ToolHandler = Callable[..., Envelope]


DEFAULT_TOOL_HANDLERS: dict[str, ToolHandler] = {
    "search_listings": search_listings,
    "listing_details": listing_details,
    "manager_rent_summary": manager_rent_summary,
}

BLOCKED_HOUSING_SEARCH_PHRASES = (
    "no children",
    "no kids",
    "no families",
    "families not allowed",
    "adults only",
    "christians only",
    "no muslims",
    "no disabled tenants",
)

SAFETY_ERROR_MESSAGE = (
    "Safety rule blocked a discriminatory "
    "housing search."
)


def _check_safety_rule(
    name: str,
    inputs: dict[str, Any],
) -> str | None:
    """Block discriminatory rental-housing searches."""

    if name != "search_listings":
        return None

    query = inputs.get("query")

    if not isinstance(query, str):
        return None

    normalized_query = " ".join(
        query.lower().split()
    )

    if any(
        phrase in normalized_query
        for phrase in BLOCKED_HOUSING_SEARCH_PHRASES
    ):
        return SAFETY_ERROR_MESSAGE

    return None


def _has_valid_envelope(result: Any) -> bool:
    return (
        isinstance(result, dict)
        and isinstance(result.get("ok"), bool)
        and "data" in result
        and "error" in result
    )


def execute_tool(
    name: str,
    inputs: dict[str, Any],
    *,
    handlers: dict[str, ToolHandler] | None = None,
) -> str:
    """Execute one domain tool and return a JSON string."""

    registry = (
        DEFAULT_TOOL_HANDLERS
        if handlers is None
        else handlers
    )

    if not isinstance(name, str) or not name.strip():
        return json.dumps(
            error_response(
                "tool name must be a non-empty string"
            )
        )

    if not isinstance(inputs, dict):
        return json.dumps(
            error_response(
                "tool inputs must be a JSON object"
            )
        )

    safety_error = _check_safety_rule(
        name,
        inputs,
    )

    if safety_error is not None:
        return json.dumps(
            error_response(safety_error)
        )

    handler = registry.get(name)

    if handler is None:
        return json.dumps(
            error_response(
                f"unknown tool: {name}"
            )
        )

    try:
        result = handler(**inputs)
    except TypeError as exc:
        return json.dumps(
            error_response(
                f"invalid inputs for {name}: {exc}"
            )
        )
    except Exception:
        logger.exception(
            "Unexpected tool failure: %s",
            name,
        )
        return json.dumps(
            error_response(
                f"{name} failed unexpectedly"
            )
        )

    if not _has_valid_envelope(result):
        logger.error(
            "Tool returned an invalid envelope: %s",
            name,
        )
        result = error_response(
            f"{name} returned an invalid result"
        )

    return json.dumps(
        result,
        ensure_ascii=False,
        default=str,
    )