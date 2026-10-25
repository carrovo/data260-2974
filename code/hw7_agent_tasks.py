from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from hw5_agent import RELIABILITY_CATEGORIES


@dataclass(frozen=True)
class AgentTaskSpec:
    key: str
    prompt: str
    required_tool_sequence: tuple[str, ...]


TASK_A = AgentTaskSpec(
    key="A",
    prompt=(
        'Search for rental listings using the domain term "Shared Room" '
        "with limit 1. Then take the id of the first returned result and "
        "call listing_details for that exact id. Only after both tool "
        "calls, answer with the listing code, title, address, monthly "
        "rent, and property manager name. Do not ask me a follow-up "
        "question."
    ),
    required_tool_sequence=(
        "search_listings",
        "listing_details",
    ),
)

TASK_B = AgentTaskSpec(
    key="B",
    prompt=(
        "First call manager_rent_summary for property manager ID 1. "
        'Then call search_listings with query "S2974-000005" and limit '
        "1 to find one supporting listing managed by the same property "
        "manager. Report the listing count, average, minimum, and "
        "maximum rent, followed by the supporting listing's code and "
        "monthly rent. Do not answer until both tool calls have "
        "completed."
    ),
    required_tool_sequence=(
        "manager_rent_summary",
        "search_listings",
    ),
)

TASK_C = AgentTaskSpec(
    key="C",
    prompt=(
        'Search for rental listings using the term "Apartment" with '
        "limit 2. Take the first two distinct results and call "
        "listing_details separately for each result id. Then compare "
        "their monthly rent, available units, address, and property "
        "manager. Do not answer until the search and both detail "
        "lookups have completed."
    ),
    required_tool_sequence=(
        "search_listings",
        "listing_details",
        "listing_details",
    ),
)

TASK_SPECS = {
    task.key: task
    for task in (TASK_A, TASK_B, TASK_C)
}


def _executed_calls(run_record: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        call
        for step in run_record.get("steps", [])
        for call in step.get("tool_calls", [])
        if call.get("executed") is True
    ]


def _successful_data(call: dict[str, Any]) -> Any | None:
    result = call.get("result")

    if not isinstance(result, dict) or result.get("ok") is not True:
        return None

    return result.get("data")


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _verification_result(
    checks: dict[str, bool],
) -> dict[str, Any]:
    failed_checks = [
        name
        for name, passed in checks.items()
        if not passed
    ]

    return {
        "passed": not failed_checks,
        "checks": checks,
        "failed_checks": failed_checks,
    }


def _verify_task_a(
    run_record: dict[str, Any],
    calls: list[dict[str, Any]],
) -> dict[str, Any]:
    names = [call.get("name") for call in calls]
    search_data = (
        _successful_data(calls[0])
        if len(calls) >= 1
        else None
    )
    detail_data = (
        _successful_data(calls[1])
        if len(calls) >= 2
        else None
    )
    first_result = (
        search_data[0]
        if isinstance(search_data, list) and search_data
        else None
    )

    checks = {
        "normal_completion": (
            run_record.get("stop_reason") == "normal_completion"
        ),
        "exact_tool_sequence": names == list(
            TASK_A.required_tool_sequence
        ),
        "search_succeeded": first_result is not None,
        "detail_succeeded": isinstance(detail_data, dict),
        "detail_used_first_result_id": (
            isinstance(first_result, dict)
            and len(calls) >= 2
            and calls[1].get("inputs", {}).get("listing_id")
            == first_result.get("id")
        ),
        "detail_matches_search": (
            isinstance(first_result, dict)
            and isinstance(detail_data, dict)
            and detail_data.get("id") == first_result.get("id")
            and detail_data.get("listingCode")
            == first_result.get("listingCode")
        ),
    }

    return _verification_result(checks)


def _verify_task_b(
    run_record: dict[str, Any],
    calls: list[dict[str, Any]],
) -> dict[str, Any]:
    names = [call.get("name") for call in calls]
    summary = (
        _successful_data(calls[0])
        if len(calls) >= 1
        else None
    )
    search_data = (
        _successful_data(calls[1])
        if len(calls) >= 2
        else None
    )
    example = (
        search_data[0]
        if isinstance(search_data, list) and search_data
        else None
    )
    example_rent = (
        _decimal(example.get("monthlyRent"))
        if isinstance(example, dict)
        else None
    )
    minimum_rent = (
        _decimal(summary.get("minimumRent"))
        if isinstance(summary, dict)
        else None
    )
    maximum_rent = (
        _decimal(summary.get("maximumRent"))
        if isinstance(summary, dict)
        else None
    )

    checks = {
        "normal_completion": (
            run_record.get("stop_reason") == "normal_completion"
        ),
        "exact_tool_sequence": names == list(
            TASK_B.required_tool_sequence
        ),
        "summary_succeeded": isinstance(summary, dict),
        "summary_is_for_manager_1": (
            isinstance(summary, dict)
            and summary.get("propertyManager", {}).get("id") == 1
        ),
        "supporting_example_found": isinstance(example, dict),
        "supporting_example_has_expected_code": (
            isinstance(example, dict)
            and example.get("listingCode") == "S2974-000005"
        ),
        "supporting_example_has_same_manager": (
            isinstance(example, dict)
            and example.get("propertyManagerId") == 1
        ),
        "supporting_rent_within_summary_range": (
            example_rent is not None
            and minimum_rent is not None
            and maximum_rent is not None
            and minimum_rent <= example_rent <= maximum_rent
        ),
    }

    return _verification_result(checks)


def _verify_task_c(
    run_record: dict[str, Any],
    calls: list[dict[str, Any]],
) -> dict[str, Any]:
    names = [call.get("name") for call in calls]
    search_data = (
        _successful_data(calls[0])
        if len(calls) >= 1
        else None
    )
    details = [
        _successful_data(call)
        for call in calls[1:3]
    ]
    first_two = (
        search_data[:2]
        if isinstance(search_data, list)
        else []
    )
    search_ids = [
        item.get("id")
        for item in first_two
        if isinstance(item, dict)
    ]
    requested_ids = [
        call.get("inputs", {}).get("listing_id")
        for call in calls[1:3]
    ]
    detail_ids = [
        detail.get("id")
        for detail in details
        if isinstance(detail, dict)
    ]

    checks = {
        "normal_completion": (
            run_record.get("stop_reason") == "normal_completion"
        ),
        "exact_tool_sequence": names == list(
            TASK_C.required_tool_sequence
        ),
        "search_returned_two": len(search_ids) == 2,
        "search_ids_are_distinct": (
            len(search_ids) == 2
            and len(set(search_ids)) == 2
        ),
        "detail_requests_match_first_two": (
            requested_ids == search_ids
        ),
        "both_details_succeeded": len(detail_ids) == 2,
        "detail_results_match_requests": detail_ids == search_ids,
    }

    return _verification_result(checks)


def verify_task(
    task_key: str,
    run_record: dict[str, Any],
) -> dict[str, Any]:
    """Verify tool evidence without matching final-answer wording."""

    if task_key not in TASK_SPECS:
        raise ValueError(f"unknown task key: {task_key}")

    calls = _executed_calls(run_record)

    if task_key == "A":
        return _verify_task_a(run_record, calls)

    if task_key == "B":
        return _verify_task_b(run_record, calls)

    return _verify_task_c(run_record, calls)


def summarize_reliability(
    run_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize only the four failure classes required by HW7."""

    failure_counts = {
        category: 0
        for category in RELIABILITY_CATEGORIES
    }

    for run_record in run_records:
        for failure in run_record.get("failures", []):
            category = failure.get("category")

            if category in failure_counts:
                failure_counts[category] += 1

    return {
        "attempt_count": len(run_records),
        "failure_counts": failure_counts,
    }
