import random
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FutureTimeoutError,
)
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from sqlalchemy.exc import SQLAlchemyError


T = TypeVar("T")

_STORAGE_EXECUTOR = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="hw5-storage",
)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    timeout_seconds: float = 1.0
    base_delay_seconds: float = 0.01
    max_delay_seconds: float = 0.04


DEFAULT_RETRY_POLICY = RetryPolicy()


@dataclass(frozen=True)
class RetryOutcome:
    value: Any
    attempts: int


class RetryableStorageError(RuntimeError):
    """A temporary storage failure that may succeed on retry."""


class RetryExhaustedError(RuntimeError):
    """Raised after every permitted attempt fails."""

    def __init__(
        self,
        attempts: int,
        last_error: str,
    ) -> None:
        self.attempts = attempts
        self.last_error = last_error

        super().__init__(
            f"operation failed after {attempts} attempts: "
            f"{last_error}"
        )


class ScriptedFailureInjector:
    """Inject a predetermined sequence of failures."""

    def __init__(self, failures: list[bool]) -> None:
        self._failures = iter(failures)

    def __call__(self, attempt: int) -> None:
        should_fail = next(self._failures, False)

        if should_fail:
            raise RetryableStorageError(
                f"injected failure on attempt {attempt}"
            )


class SeededFailureInjector:
    """Inject deterministic failures using a fixed seed."""

    def __init__(
        self,
        failure_rate: float,
        seed: int,
    ) -> None:
        if not 0.0 <= failure_rate <= 1.0:
            raise ValueError(
                "failure_rate must be between 0.0 and 1.0"
            )

        self.failure_rate = failure_rate
        self._random = random.Random(seed)

    def __call__(self, attempt: int) -> None:
        if self._random.random() < self.failure_rate:
            raise RetryableStorageError(
                f"injected failure on attempt {attempt}"
            )


def run_with_retry(
    operation: Callable[[], T],
    *,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    failure_injector: Callable[[int], None] | None = None,
    retry_if_result: Callable[[T], bool] | None = None,
    trace: list[dict[str, Any]] | None = None,
) -> RetryOutcome:
    """Run one operation with timeout and bounded backoff."""

    for attempt in range(1, policy.max_attempts + 1):
        attempt_started = time.perf_counter()

        try:
            if failure_injector is not None:
                failure_injector(attempt)

            future = _STORAGE_EXECUTOR.submit(operation)

            value = future.result(
                timeout=policy.timeout_seconds
            )

            if (
                retry_if_result is not None
                and retry_if_result(value)
            ):
                raise RetryableStorageError(
                    "storage operation returned "
                    "a retryable error"
                )

            elapsed_ms = (
                time.perf_counter() - attempt_started
            ) * 1000.0

            if trace is not None:
                trace.append(
                    {
                        "attempt": attempt,
                        "status": "success",
                        "latency_ms": round(
                            elapsed_ms,
                            3,
                        ),
                    }
                )

            return RetryOutcome(
                value=value,
                attempts=attempt,
            )

        except (
            FutureTimeoutError,
            RetryableStorageError,
            SQLAlchemyError,
        ) as exc:
            elapsed_ms = (
                time.perf_counter() - attempt_started
            ) * 1000.0

            if trace is not None:
                trace.append(
                    {
                        "attempt": attempt,
                        "status": "failure",
                        "error": str(exc),
                        "latency_ms": round(
                            elapsed_ms,
                            3,
                        ),
                    }
                )

            if attempt == policy.max_attempts:
                raise RetryExhaustedError(
                    attempts=attempt,
                    last_error=str(exc),
                ) from exc

            delay = min(
                policy.base_delay_seconds
                * (2 ** (attempt - 1)),
                policy.max_delay_seconds,
            )
            time.sleep(delay)

    raise RuntimeError("retry loop ended unexpectedly")