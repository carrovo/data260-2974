import json
from datetime import datetime

from tool_executor import execute_tool


STUDENT_NAME = "Xuanhua Li"
SID4 = 2974


def main() -> None:
    print(f"Student: {STUDENT_NAME} | SID4: {SID4}")
    print(
        "Timestamp:",
        datetime.now().astimezone().isoformat(),
    )

    allowed_raw = execute_tool(
        "search_listings",
        {
            "query": "Apartment",
            "limit": 1,
        },
    )

    blocked_raw = execute_tool(
        "search_listings",
        {
            "query": "no families with children",
            "limit": 5,
        },
    )

    allowed = json.loads(allowed_raw)
    blocked = json.loads(blocked_raw)

    print("\nALLOWED CALL")
    print(
        json.dumps(
            {
                "input": {
                    "query": "Apartment",
                    "limit": 1,
                },
                "ok": allowed["ok"],
                "error": allowed["error"],
            },
            indent=2,
        )
    )

    print("\nBLOCKED CALL")
    print(
        json.dumps(
            {
                "input": {
                    "query":
                        "no families with children",
                    "limit": 5,
                },
                "ok": blocked["ok"],
                "data": blocked["data"],
                "error": blocked["error"],
            },
            indent=2,
        )
    )

    assert allowed["ok"] is True
    assert blocked == {
        "ok": False,
        "data": None,
        "error": (
            "Safety rule blocked a discriminatory "
            "housing search."
        ),
    }

    print("\nSAFETY RULE DEMONSTRATION: 2/2 PASS")


if __name__ == "__main__":
    main()