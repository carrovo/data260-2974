import json
import os
from collections.abc import Callable

# Force this test process to use an offline database URL
# before importing the application modules.
os.environ["DATABASE_URL"] = (
    "sqlite+pysqlite:///:memory:"
)

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

import domain_tools
from tool_executor import execute_tool


STUDENT_NAME = "Xuanhua Li"
SID4 = 2974


def create_fixture_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE property_managers (
                id INTEGER PRIMARY KEY,
                firstName VARCHAR(100) NOT NULL,
                lastName VARCHAR(100) NOT NULL,
                email VARCHAR(255) NOT NULL UNIQUE
            )
            """
        )

        connection.exec_driver_sql(
            """
            CREATE TABLE listings (
                id INTEGER PRIMARY KEY,
                listingCode VARCHAR(30) NOT NULL UNIQUE,
                listingTitle VARCHAR(100) NOT NULL,
                address VARCHAR(200) NOT NULL,
                submitterEmail VARCHAR(200) NOT NULL,
                description TEXT NOT NULL,
                propertyType VARCHAR(30) NOT NULL,
                monthlyRent NUMERIC(10, 2) NOT NULL,
                availableUnits INTEGER NOT NULL,
                termsAccepted INTEGER NOT NULL,
                propertyManagerId INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )

        connection.execute(
            text(
                """
                INSERT INTO property_managers (
                    id,
                    firstName,
                    lastName,
                    email
                )
                VALUES (
                    1,
                    'Offline',
                    'Manager',
                    'offline.manager@example.com'
                )
                """
            )
        )

        connection.execute(
            text(
                """
                INSERT INTO listings (
                    id,
                    listingCode,
                    listingTitle,
                    address,
                    submitterEmail,
                    description,
                    propertyType,
                    monthlyRent,
                    availableUnits,
                    termsAccepted,
                    propertyManagerId,
                    created_at,
                    updated_at
                )
                VALUES (
                    4,
                    'S2974-OFFLINE-004',
                    'Offline Test Apartment',
                    '400 Offline Avenue',
                    'offline.owner@example.com',
                    'Temporary offline test fixture.',
                    'Apartment',
                    1700.00,
                    2,
                    1,
                    1,
                    '2026-10-04 12:00:00',
                    '2026-10-04 12:00:00'
                )
                """
            )
        )

    return engine


def parse_result(
    tool_name: str,
    inputs: dict,
) -> dict:
    raw_result = execute_tool(
        tool_name,
        inputs,
    )

    assert isinstance(raw_result, str)

    result = json.loads(raw_result)

    assert set(result) == {
        "ok",
        "data",
        "error",
    }

    return result


def test_search_valid() -> None:
    result = parse_result(
        "search_listings",
        {
            "query": "Offline",
            "limit": 5,
        },
    )

    assert result["ok"] is True
    assert len(result["data"]) == 1
    assert (
        result["data"][0]["listingCode"]
        == "S2974-OFFLINE-004"
    )


def test_search_invalid() -> None:
    result = parse_result(
        "search_listings",
        {
            "query": "Offline",
            "limit": 0,
        },
    )

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"] == (
        "limit must be an integer between 1 and 25"
    )


def test_detail_valid() -> None:
    result = parse_result(
        "listing_details",
        {
            "listing_id": 4,
        },
    )

    assert result["ok"] is True
    assert result["data"]["id"] == 4
    assert (
        result["data"]["propertyManager"]["id"]
        == 1
    )


def test_detail_invalid() -> None:
    result = parse_result(
        "listing_details",
        {
            "listing_id": -1,
        },
    )

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"] == (
        "listing_id must be a positive integer"
    )


def test_aggregate_valid() -> None:
    result = parse_result(
        "manager_rent_summary",
        {
            "property_manager_id": 1,
        },
    )

    assert result["ok"] is True
    assert result["data"]["listingCount"] == 1
    assert (
        result["data"]["totalAvailableUnits"]
        == 2
    )
    assert result["data"]["averageRent"] == (
        "1700.00"
    )


def test_aggregate_invalid() -> None:
    result = parse_result(
        "manager_rent_summary",
        {
            "property_manager_id": -1,
        },
    )

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"] == (
        "property_manager_id must be a "
        "positive integer"
    )


def test_unknown_tool() -> None:
    result = parse_result(
        "delete_everything",
        {},
    )

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"] == (
        "unknown tool: delete_everything"
    )


def test_non_object_inputs() -> None:
    raw_result = execute_tool(
        "search_listings",
        ["Offline"],
    )
    result = json.loads(raw_result)

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"] == (
        "tool inputs must be a JSON object"
    )


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("search valid", test_search_valid),
    ("search invalid", test_search_invalid),
    ("detail valid", test_detail_valid),
    ("detail invalid", test_detail_invalid),
    ("aggregate valid", test_aggregate_valid),
    ("aggregate invalid", test_aggregate_invalid),
    ("unknown tool", test_unknown_tool),
    ("non-object inputs", test_non_object_inputs),
]


def main() -> None:
    print(f"Student: {STUDENT_NAME} | SID4: {SID4}")
    print("HW5 PART 4 OFFLINE TOOL TESTS")
    print("Database: temporary in-memory SQLite fixture")
    print("LLM: not used\n")

    fixture_engine = create_fixture_engine()
    original_engine = domain_tools.db_session_basede26
    domain_tools.db_session_basede26 = fixture_engine

    passed = 0

    try:
        for name, test_function in TESTS:
            try:
                test_function()
            except Exception as exc:
                print(f"FAIL | {name} | {exc}")
            else:
                passed += 1
                print(f"PASS | {name}")
    finally:
        domain_tools.db_session_basede26 = (
            original_engine
        )
        fixture_engine.dispose()

    total = len(TESTS)

    print(f"\nFINAL SUMMARY: {passed}/{total} PASS")

    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()