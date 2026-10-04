import json
from datetime import datetime

from reliable_domain_tools import listing_details
from retry_policy import ScriptedFailureInjector


STUDENT_NAME = "Xuanhua Li"
SID4 = 2974


def run_scenario(
    name: str,
    failures: list[bool],
) -> tuple[dict, list[dict]]:
    trace: list[dict] = []

    result = listing_details(
        4,
        failure_injector=ScriptedFailureInjector(
            failures
        ),
        retry_trace=trace,
    )

    print(f"\n{name}")
    print("Result:")
    print(json.dumps(result, indent=2))
    print("Retry trace:")
    print(json.dumps(trace, indent=2))

    return result, trace


def main() -> None:
    print(f"Student: {STUDENT_NAME} | SID4: {SID4}")
    print(
        "Timestamp:",
        datetime.now().astimezone().isoformat(),
    )

    first_result, first_trace = run_scenario(
        "SCENARIO 1: SUCCESS ON FIRST ATTEMPT",
        [False],
    )

    retry_result, retry_trace = run_scenario(
        "SCENARIO 2: FIRST ATTEMPT FAILS, "
        "SECOND SUCCEEDS",
        [True, False],
    )

    failed_result, failed_trace = run_scenario(
        "SCENARIO 3: ALL ATTEMPTS FAIL",
        [True, True, True],
    )

    assert first_result["ok"] is True
    assert len(first_trace) == 1
    assert first_trace[0]["status"] == "success"

    assert retry_result["ok"] is True
    assert len(retry_trace) == 2
    assert retry_trace[0]["status"] == "failure"
    assert retry_trace[1]["status"] == "success"

    assert failed_result["ok"] is False
    assert len(failed_trace) == 3
    assert all(
        item["status"] == "failure"
        for item in failed_trace
    )
    assert failed_result["error"] == (
        "database operation failed after 3 attempts"
    )

    print("\nRETRY DEMONSTRATION: 3/3 PASS")


if __name__ == "__main__":
    main()