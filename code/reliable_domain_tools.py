from typing import Any, Callable

from domain_tools import error_response
from domain_tools import (
    listing_details as raw_listing_details,
)
from domain_tools import (
    manager_rent_summary as raw_manager_rent_summary,
)
from domain_tools import (
    search_listings as raw_search_listings,
)
from retry_policy import (
    DEFAULT_RETRY_POLICY,
    RetryExhaustedError,
    RetryPolicy,
    run_with_retry,
)


Envelope = dict[str, Any]
FailureInjector = Callable[[int], None]


def _is_retryable_result(result: Envelope) -> bool:
    return (
        result.get("ok") is False
        and result.get("error")
        == "database operation failed"
    )


def _run_reliably(
    operation: Callable[[], Envelope],
    *,
    policy: RetryPolicy,
    failure_injector: FailureInjector | None,
    retry_trace: list[dict[str, Any]] | None,
) -> Envelope:
    try:
        outcome = run_with_retry(
            operation,
            policy=policy,
            failure_injector=failure_injector,
            retry_if_result=_is_retryable_result,
            trace=retry_trace,
        )
    except RetryExhaustedError as exc:
        return error_response(
            "database operation failed after "
            f"{exc.attempts} attempts"
        )

    return outcome.value


def search_listings(
    query: str,
    limit: int = 5,
    *,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    failure_injector: FailureInjector | None = None,
    retry_trace: list[dict[str, Any]] | None = None,
) -> Envelope:
    return _run_reliably(
        lambda: raw_search_listings(query, limit),
        policy=policy,
        failure_injector=failure_injector,
        retry_trace=retry_trace,
    )


def listing_details(
    listing_id: int,
    *,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    failure_injector: FailureInjector | None = None,
    retry_trace: list[dict[str, Any]] | None = None,
) -> Envelope:
    return _run_reliably(
        lambda: raw_listing_details(listing_id),
        policy=policy,
        failure_injector=failure_injector,
        retry_trace=retry_trace,
    )


def manager_rent_summary(
    property_manager_id: int,
    *,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    failure_injector: FailureInjector | None = None,
    retry_trace: list[dict[str, Any]] | None = None,
) -> Envelope:
    return _run_reliably(
        lambda: raw_manager_rent_summary(
            property_manager_id
        ),
        policy=policy,
        failure_injector=failure_injector,
        retry_trace=retry_trace,
    )