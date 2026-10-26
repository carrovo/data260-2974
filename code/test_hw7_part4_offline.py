# ruff: noqa: E402

import csv
import hashlib
import io
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = PROJECT_ROOT / "code"

if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from hw7_part4_data import (
    generate_scenarios,
    verify_outputs,
)
from hw7_part4_tools import (
    PART4_TOOL_SCHEMAS,
    PRICING_FINAL_URL,
    PRICING_URL,
    FetchedPage,
    calculator,
    capture_policy_snapshot,
    csv_sql,
    extract_pricing_rules,
    parse_policy_passages,
    policy_retriever,
    validate_part4_inputs,
    verify_snapshot_hash,
)

FIXTURE_HTML = CODE_ROOT / "fixtures" / "hw7_part4" / "pricing_fixture.html"
TEST_TMP_ROOT = PROJECT_ROOT / "tmp"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


def _fixture_page(_url: str) -> FetchedPage:
    return FetchedPage(
        content=FIXTURE_HTML.read_bytes(),
        final_url=PRICING_FINAL_URL,
        status_code=200,
    )


def _write_uploaded_csv(path: Path, rows: int = 150) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=["ride_id", "duration_seconds", "scenario_target"],
            lineterminator="\n",
        )
        writer.writeheader()

        for index in range(rows):
            writer.writerow(
                {
                    "ride_id": f"TEST-{index:04d}",
                    "duration_seconds": str(300 + index),
                    "scenario_target": "true" if index < 2 else "false",
                }
            )


def test_json_schemas_and_strict_validation() -> None:
    schemas = {
        schema["function"]["name"]: schema
        for schema in PART4_TOOL_SCHEMAS
    }

    assert set(schemas) == {"csv_sql", "policy_retriever", "calculator"}

    for schema in schemas.values():
        assert schema["function"]["parameters"]["additionalProperties"] is False

    invalid_cases = [
        ("csv_sql", {"sql": "SELECT 1", "extra": True}),
        ("csv_sql", {"sql": 123}),
        (
            "policy_retriever",
            {"url": "https://example.com/pricing", "query": "month"},
        ),
        (
            "policy_retriever",
            {"url": PRICING_URL, "query": "month", "k": True},
        ),
        ("calculator", {"expression": "1+2", "units": 3}),
    ]

    for name, inputs in invalid_cases:
        try:
            validate_part4_inputs(name, inputs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"validation unexpectedly accepted {name}: {inputs}")


def test_csv_sql_success_and_row_limit() -> None:
    with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
        csv_path = Path(temp) / "uploaded.csv"
        _write_uploaded_csv(csv_path)
        count = csv_sql(
            {"sql": "SELECT COUNT(*) AS ride_count FROM trips"},
            csv_path=csv_path,
        )
        cte = csv_sql(
            {
                "sql": (
                    "WITH targets AS (SELECT * FROM trips "
                    "WHERE scenario_target = 'true') "
                    "SELECT ride_id FROM targets ORDER BY ride_id"
                )
            },
            csv_path=csv_path,
        )
        bounded = csv_sql(
            {"sql": "SELECT ride_id FROM trips ORDER BY ride_id"},
            csv_path=csv_path,
        )

    assert count["success"] is True
    assert count["data"] == {
        "rows": [{"ride_count": 150}],
        "row_count": 1,
        "source": "uploaded.csv",
    }
    assert cte["success"] is True
    assert cte["data"]["row_count"] == 2
    assert bounded["success"] is True
    assert bounded["data"]["row_count"] == 100


def test_csv_sql_readonly_boundary() -> None:
    statements = [
        "INSERT INTO trips VALUES ('x', '1', 'false')",
        "UPDATE trips SET ride_id = 'x'",
        "DELETE FROM trips",
        "DROP TABLE trips",
        "ALTER TABLE trips ADD COLUMN x TEXT",
        "ATTACH DATABASE '/tmp/other.db' AS other",
        "PRAGMA table_info(trips)",
        "COPY trips TO '/tmp/out.csv'",
        "SELECT * FROM trips; SELECT * FROM trips",
        "SELECT readfile('/etc/passwd')",
        "SELECT printf('%1000000000s', 'x')",
        "SELECT * FROM sqlite_master",
        "WITH doomed AS (DELETE FROM trips RETURNING *) SELECT * FROM doomed",
        "SELECT * FROM trips -- hidden text",
    ]

    with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
        csv_path = Path(temp) / "uploaded.csv"
        _write_uploaded_csv(csv_path, rows=5)

        for statement in statements:
            result = csv_sql({"sql": statement}, csv_path=csv_path)
            assert result["success"] is False, statement
            assert result["error"], statement


def test_calculator_success_and_failures() -> None:
    success = calculator(
        {"expression": "29 + 2 * (1 + 10 * 0.19)", "units": "USD"}
    )
    assert success["success"] is True
    assert success["data"]["value"] == 34.8
    assert success["data"]["units"] == "USD"

    invalid = [
        "1 / 0",
        "2 ** 3",
        "7 // 2",
        "2 ^ 3",
        "abs(1)",
        "__import__('os').system('id')",
        "9" * 200 + " * " + "9" * 50,
    ]

    for expression in invalid:
        result = calculator({"expression": expression})
        assert result["success"] is False, expression


def test_policy_fixture_parser_and_retriever() -> None:
    html = FIXTURE_HTML.read_bytes()
    passages = parse_policy_passages(html, source=PRICING_FINAL_URL)
    rules = extract_pricing_rules(passages)
    result = policy_retriever(
        {
            "url": PRICING_URL,
            "query": "monthly price month pass",
            "k": 2,
        },
        fetcher=_fixture_page,
    )

    assert rules["month_pass"]["amount"] == "29"
    assert rules["classic_non_member"] == {
        "unlock_fee": "1",
        "per_minute": "0.19",
        "evidence": "Classic bike: $1 to unlock, then $0.19/min.",
    }
    assert rules["classic_member"]["included_minutes"] == 45
    assert rules["classic_member"]["overage_per_minute"] == "0.17"
    assert rules["ebike_non_member"]["per_minute"] == "0.49"
    assert rules["ebike_member"]["per_minute"] == "0.17"
    assert result["success"] is True
    assert result["source"] == PRICING_FINAL_URL
    assert result["data"]["passages"][0]["score"] > 0
    assert "$29/month" in result["data"]["passages"][0]["text"]

    retrieval_checks = {
        "classic single unlock per minute": "$0.19/min",
        "classic member 45 minute inclusion overage": "45 minutes",
        "non-member ebike unlock rate": "$0.49/min",
        "member ebike rate": "Member ebike rate: $0.17/min",
    }

    for query, expected_text in retrieval_checks.items():
        retrieved = policy_retriever(
            {"url": PRICING_URL, "query": query, "k": 3},
            fetcher=_fixture_page,
        )
        returned_text = "\n".join(
            passage["text"]
            for passage in retrieved["data"]["passages"]
        )
        assert expected_text in returned_text, query


def test_policy_failure_and_schema_errors() -> None:
    def failing_fetcher(_url: str) -> FetchedPage:
        raise OSError("controlled offline fetch failure")

    failed = policy_retriever(
        {"url": PRICING_URL, "query": "ebike"},
        fetcher=failing_fetcher,
    )
    extra = policy_retriever(
        {"url": PRICING_URL, "query": "ebike", "extra": "no"},
        fetcher=_fixture_page,
    )

    assert failed["success"] is False
    assert "controlled offline fetch failure" in failed["error"]
    assert extra["success"] is False
    assert "unknown field" in extra["error"]


def _write_test_archive(path: Path, rows: int = 650) -> None:
    buffer = io.StringIO(newline="")
    fieldnames = [
        "ride_id",
        "rideable_type",
        "started_at",
        "ended_at",
        "start_station_name",
        "end_station_name",
        "member_casual",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    base = datetime(2024, 1, 1, 8, 0, 0)

    for index in range(rows):
        started = base + timedelta(minutes=index * 3)
        duration = 120 + index % 1_200
        ended = started + timedelta(seconds=duration)
        writer.writerow(
            {
                "ride_id": f"SYNTHETIC-TEST-{index:05d}",
                "rideable_type": (
                    "classic_bike" if index % 4 else "electric_bike"
                ),
                "started_at": started.isoformat(sep=" "),
                "ended_at": ended.isoformat(sep=" "),
                "start_station_name": "Test Start",
                "end_station_name": "Test End",
                "member_casual": "casual",
            }
        )

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("test-only-tripdata.csv", buffer.getvalue())


def test_snapshot_hash_and_opposite_acceptance_scenarios() -> None:
    with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
        root = Path(temp)
        html_path = root / "pricing_fixture.html"
        snapshot_path = root / "pricing_snapshot.json"
        archive_path = root / "synthetic-test-only.zip"
        output_dir = root / "scenarios"
        snapshot = capture_policy_snapshot(
            url=PRICING_URL,
            html_path=html_path,
            snapshot_path=snapshot_path,
            fetcher=_fixture_page,
            capture_kind="fixed_test_fixture_not_official",
        )
        _write_test_archive(archive_path)
        archive_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        metadata = {
            "data_classification": "synthetic_test_fixture_not_official",
            "url": "test-fixture://synthetic-test-only.zip",
            "final_url": "test-fixture://synthetic-test-only.zip",
            "month": "202401",
            "bytes": archive_path.stat().st_size,
            "sha256": archive_hash,
            "local_file": "temporary-test-fixture",
        }
        manifest = generate_scenarios(
            archive_path=archive_path,
            archive_metadata=metadata,
            snapshot_path=snapshot_path,
            output_dir=output_dir,
        )
        verification = verify_outputs(
            snapshot_path=snapshot_path,
            manifest_path=output_dir / "transformation_manifest.json",
        )
        high, low = manifest["scenarios"]

        assert snapshot["capture_kind"] == "fixed_test_fixture_not_official"
        assert verify_snapshot_hash(snapshot_path) is True
        assert snapshot["html_sha256"] == hashlib.sha256(
            FIXTURE_HTML.read_bytes()
        ).hexdigest()
        assert high["total_rows"] == 600
        assert high["target_ride_count"] == 40
        assert high["expected_winning_option"] == "membership"
        assert float(high["acceptance_costs_usd"]["membership"]) < float(
            high["acceptance_costs_usd"]["pay_per_use"]
        )
        assert low["total_rows"] == 600
        assert low["target_ride_count"] == 2
        assert low["expected_winning_option"] == "pay_per_use"
        assert float(low["acceptance_costs_usd"]["pay_per_use"]) < float(
            low["acceptance_costs_usd"]["membership"]
        )
        assert verification["snapshot_hash_matches"] is True
        assert all(
            item["row_count"] >= 500
            for item in verification["scenarios"]
        )
        assert "TEST-ONLY" in manifest["transformation"][
            "scenario_overlay_disclosure"
        ]

        for csv_path in output_dir.glob("*.csv"):
            assert b"\r" not in csv_path.read_bytes()


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("JSON schemas and strict validation", test_json_schemas_and_strict_validation),
    ("csv_sql success and row limit", test_csv_sql_success_and_row_limit),
    ("csv_sql read-only boundary", test_csv_sql_readonly_boundary),
    ("calculator success and failures", test_calculator_success_and_failures),
    ("policy fixture parser and retriever", test_policy_fixture_parser_and_retriever),
    ("policy failures and schema errors", test_policy_failure_and_schema_errors),
    (
        "snapshot hash and opposite acceptance scenarios",
        test_snapshot_hash_and_opposite_acceptance_scenarios,
    ),
]


def main() -> None:
    print("HW7 PART 4 OFFLINE TOOL + DATA TESTS")
    print("Policy HTML and trip rows: explicitly test-only fixtures")
    print("No model, official network, or personal database is used\n")
    passed = 0

    for name, test_function in TESTS:
        try:
            test_function()
        except Exception as exc:
            print(f"FAIL | {name} | {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"PASS | {name}")

    print(f"\nFINAL SUMMARY: {passed}/{len(TESTS)} PASS")

    if passed != len(TESTS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
