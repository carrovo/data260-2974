import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hw7_part4_tools import (  # noqa: E402
    PRICING_URL,
    capture_policy_snapshot,
    verify_snapshot_hash,
)

DEFAULT_ARCHIVE_MONTH = "202401"
DEFAULT_ARCHIVE_FILENAME = (
    f"{DEFAULT_ARCHIVE_MONTH}-baywheels-tripdata.csv.zip"
)
DEFAULT_ARCHIVE_URL = (
    "https://s3.amazonaws.com/baywheels-data/"
    f"{DEFAULT_ARCHIVE_FILENAME}"
)
ARCHIVE_INDEX_URL = "https://s3.amazonaws.com/baywheels-data/index.html"
SYSTEM_DATA_URL = "https://www.lyft.com/bikes/bay-wheels/system-data"
MAX_ARCHIVE_BYTES = 750_000_000
MAX_SOURCE_SCAN_ROWS = 100_000
SCENARIO_ROW_COUNT = 600
HIGH_TARGET_COUNT = 40
LOW_TARGET_COUNT = 2
MEMBERSHIP_MIN_DURATION_SECONDS = Decimal("60")
MEMBERSHIP_MAX_DURATION_SECONDS = Decimal("2700")
PAY_PER_USE_MIN_DURATION_SECONDS = Decimal("300")
PAY_PER_USE_MAX_DURATION_SECONDS = Decimal("900")
DATA_DIR = PROJECT_ROOT / "reports" / "hw07" / "data" / "part4"
POLICY_DIR = DATA_DIR / "policy"
SCENARIO_DIR = DATA_DIR / "scenarios"
DEFAULT_HTML_PATH = POLICY_DIR / "pricing_page.html"
DEFAULT_SNAPSHOT_PATH = POLICY_DIR / "pricing_snapshot.json"
DEFAULT_CACHE_DIR = PROJECT_ROOT / "tmp" / "hw7-part4"
DEFAULT_ARCHIVE_PATH = DEFAULT_CACHE_DIR / DEFAULT_ARCHIVE_FILENAME
DEFAULT_MANIFEST_PATH = SCENARIO_DIR / "transformation_manifest.json"
DEFAULT_SUMMARY_PATH = SCENARIO_DIR / "scenario_summary.json"
MONTH_PATTERN = re.compile(r"^\d{6}$")


class Part4DataError(RuntimeError):
    """Raised when official inputs or acceptance invariants fail."""


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1_048_576), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _validate_archive_url(url: str, month: str) -> None:
    if (
        MONTH_PATTERN.fullmatch(month) is None
        or month != DEFAULT_ARCHIVE_MONTH
    ):
        raise Part4DataError(
            f"month must be the pinned value {DEFAULT_ARCHIVE_MONTH}"
        )

    parsed = urlsplit(url)
    allowed_locations = {
        (
            "s3.amazonaws.com",
            f"/baywheels-data/{DEFAULT_ARCHIVE_FILENAME}",
        ),
        (
            "baywheels-data.s3.amazonaws.com",
            f"/{DEFAULT_ARCHIVE_FILENAME}",
        ),
    }

    if (
        parsed.scheme != "https"
        or (parsed.hostname, parsed.path) not in allowed_locations
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.query
        or parsed.fragment
    ):
        raise Part4DataError(
            "archive URL must be the pinned monthly file in the official "
            "baywheels-data S3 bucket"
        )


def download_archive(
    *,
    url: str,
    month: str,
    destination: Path,
) -> dict[str, Any]:
    _validate_archive_url(url, month)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256()
    size = 0

    try:
        with requests.get(
            url,
            headers={"User-Agent": "DATA260-HW7-trip-data/1.0"},
            timeout=(10, 120),
            stream=True,
            allow_redirects=True,
        ) as response:
            response.raise_for_status()
            _validate_archive_url(response.url, month)
            content_length = response.headers.get("Content-Length")

            if content_length and int(content_length) > MAX_ARCHIVE_BYTES:
                raise Part4DataError(
                    f"archive exceeds {MAX_ARCHIVE_BYTES} bytes"
                )

            with temporary.open("wb") as output:
                for chunk in response.iter_content(chunk_size=1_048_576):
                    if not chunk:
                        continue

                    size += len(chunk)

                    if size > MAX_ARCHIVE_BYTES:
                        raise Part4DataError(
                            f"archive exceeds {MAX_ARCHIVE_BYTES} bytes"
                        )

                    digest.update(chunk)
                    output.write(chunk)

        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    if not zipfile.is_zipfile(destination):
        destination.unlink(missing_ok=True)
        raise Part4DataError("downloaded archive is not a valid ZIP file")

    return {
        "data_classification": "official_public_archive",
        "url": url,
        "final_url": response.url,
        "month": month,
        "bytes": size,
        "sha256": digest.hexdigest(),
        "local_file": str(destination.relative_to(PROJECT_ROOT)),
    }


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        for format_string in (
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%m/%d/%Y %H:%M",
        ):
            try:
                return datetime.strptime(normalized, format_string)
            except ValueError:
                continue

    raise Part4DataError(f"unsupported trip timestamp: {value!r}")


def _first_present(row: dict[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        value = row.get(name)

        if value is not None and value.strip():
            return value.strip()

    return None


def ride_duration_seconds(row: dict[str, str]) -> Decimal:
    direct = _first_present(
        row,
        ("duration_sec", "duration_seconds", "duration"),
    )

    if direct is not None:
        duration = Decimal(direct)
    else:
        started = _first_present(row, ("started_at", "start_time"))
        ended = _first_present(row, ("ended_at", "end_time"))

        if started is None or ended is None:
            raise Part4DataError("trip row has no usable duration fields")

        duration = Decimal(str((_parse_datetime(ended) - _parse_datetime(started)).total_seconds()))

    if duration <= 0:
        raise Part4DataError("trip duration must be positive")

    return duration


def ride_start(row: dict[str, str]) -> datetime:
    value = _first_present(row, ("started_at", "start_time"))

    if value is None:
        raise Part4DataError("trip row has no start timestamp")

    return _parse_datetime(value)


def ride_kind(row: dict[str, str]) -> str:
    value = _first_present(row, ("rideable_type", "bike_type"))

    if value is None:
        return "unknown"

    lowered = value.lower().replace("-", "_")

    if "electric" in lowered or "ebike" in lowered or "e_bike" in lowered:
        return "ebike"

    if "classic" in lowered or "docked" in lowered:
        return "classic"

    return "unknown"


def is_classic_bike_source_row(row: dict[str, str]) -> bool:
    value = _first_present(row, ("rideable_type", "bike_type"))

    if value is None:
        return False

    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")

    return normalized in {"classic", "classic_bike"}


@dataclass(frozen=True)
class SourceRide:
    source_row_number: int
    row: dict[str, str]
    duration_seconds: Decimal
    started_at: datetime
    kind: str


def _iter_archive_rows(
    archive_path: Path,
) -> tuple[str, list[str], Iterator[dict[str, str]]]:
    if not zipfile.is_zipfile(archive_path):
        raise Part4DataError("source archive is not a valid ZIP file")

    archive = zipfile.ZipFile(archive_path)
    members = sorted(
        name
        for name in archive.namelist()
        if name.lower().endswith(".csv") and not name.startswith("__MACOSX/")
    )

    if not members:
        archive.close()
        raise Part4DataError("source archive contains no CSV member")

    member = members[0]
    binary = archive.open(member)
    text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
    reader = csv.DictReader(text)
    fieldnames = reader.fieldnames

    if not fieldnames:
        text.close()
        archive.close()
        raise Part4DataError("source CSV has no header")

    def rows() -> Iterator[dict[str, str]]:
        try:
            for row in reader:
                yield {name: row.get(name, "") for name in fieldnames}
        finally:
            text.close()
            archive.close()

    return member, fieldnames, rows()


def load_source_rides(
    archive_path: Path,
) -> tuple[str, list[str], list[SourceRide], int]:
    member, fieldnames, rows = _iter_archive_rows(archive_path)
    valid: list[SourceRide] = []
    scanned = 0

    for source_row_number, row in enumerate(rows, start=2):
        scanned += 1

        if scanned > MAX_SOURCE_SCAN_ROWS:
            break

        try:
            duration = ride_duration_seconds(row)
            started = ride_start(row)
        except (ArithmeticError, Part4DataError, ValueError):
            continue

        valid.append(
            SourceRide(
                source_row_number=source_row_number,
                row=row,
                duration_seconds=duration,
                started_at=started,
                kind=ride_kind(row),
            )
        )

    rows.close()

    if len(valid) < SCENARIO_ROW_COUNT:
        raise Part4DataError(
            f"archive supplied only {len(valid)} usable rows; "
            f"{SCENARIO_ROW_COUNT} are required"
        )

    return member, fieldnames, valid, scanned


def _pricing_decimal(rules: dict[str, Any], *path: str) -> Decimal:
    value: Any = rules

    for key in path:
        value = value[key]

    return Decimal(str(value))


def calculate_costs(
    rides: list[SourceRide],
    pricing_rules: dict[str, Any],
) -> dict[str, str]:
    member_total = _pricing_decimal(pricing_rules, "month_pass", "amount")
    pay_total = Decimal("0")
    included = _pricing_decimal(
        pricing_rules,
        "classic_member",
        "included_minutes",
    )

    for ride in rides:
        minutes = ride.duration_seconds / Decimal("60")

        if ride.kind == "classic":
            pay_total += _pricing_decimal(
                pricing_rules,
                "classic_non_member",
                "unlock_fee",
            )
            pay_total += minutes * _pricing_decimal(
                pricing_rules,
                "classic_non_member",
                "per_minute",
            )
            overage = max(Decimal("0"), minutes - included)
            member_total += overage * _pricing_decimal(
                pricing_rules,
                "classic_member",
                "overage_per_minute",
            )
        elif ride.kind == "ebike":
            pay_total += _pricing_decimal(
                pricing_rules,
                "ebike_non_member",
                "unlock_fee",
            )
            pay_total += minutes * _pricing_decimal(
                pricing_rules,
                "ebike_non_member",
                "per_minute",
            )
            member_total += minutes * _pricing_decimal(
                pricing_rules,
                "ebike_member",
                "per_minute",
            )
        else:
            raise Part4DataError(
                "target ride has an unsupported rideable_type"
            )

    cents = Decimal("0.01")

    return {
        "membership": str(member_total.quantize(cents, rounding=ROUND_HALF_UP)),
        "pay_per_use": str(pay_total.quantize(cents, rounding=ROUND_HALF_UP)),
    }


def _scenario_rows(
    rides: list[SourceRide],
    targets: list[SourceRide],
) -> list[tuple[SourceRide, bool]]:
    target_numbers = {ride.source_row_number for ride in targets}
    selected: list[SourceRide] = list(targets)
    selected_numbers = set(target_numbers)

    for ride in rides:
        if len(selected) >= SCENARIO_ROW_COUNT:
            break

        if ride.source_row_number not in selected_numbers:
            selected.append(ride)
            selected_numbers.add(ride.source_row_number)

    selected.sort(key=lambda ride: ride.source_row_number)

    if len(selected) != SCENARIO_ROW_COUNT:
        raise Part4DataError(
            f"scenario must contain exactly {SCENARIO_ROW_COUNT} source rows"
        )

    return [
        (ride, ride.source_row_number in target_numbers)
        for ride in selected
    ]


def _write_scenario_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[tuple[SourceRide, bool]],
) -> str:
    output_fields = [*fieldnames, "scenario_target"]
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=output_fields,
            lineterminator="\n",
        )
        writer.writeheader()

        for ride, target in rows:
            writer.writerow(
                {
                    **ride.row,
                    "scenario_target": "true" if target else "false",
                }
            )

    _verify_written_source_facts(path, fieldnames, rows)

    return _sha256(path)


def _verify_written_source_facts(
    path: Path,
    fieldnames: list[str],
    expected_rows: list[tuple[SourceRide, bool]],
) -> None:
    with path.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        actual_rows = list(reader)

    expected_fields = [*fieldnames, "scenario_target"]

    if reader.fieldnames != expected_fields:
        raise Part4DataError(
            "scenario output fields differ from source fields plus "
            "scenario_target"
        )

    if len(actual_rows) != len(expected_rows) == SCENARIO_ROW_COUNT:
        raise Part4DataError(
            f"scenario output must contain exactly {SCENARIO_ROW_COUNT} rows"
        )

    for actual, (ride, target) in zip(actual_rows, expected_rows, strict=True):
        actual_target = actual.pop("scenario_target", None)

        if actual_target != ("true" if target else "false"):
            raise Part4DataError("scenario_target overlay changed unexpectedly")

        if actual != ride.row:
            raise Part4DataError(
                "scenario generation changed one or more source trip facts"
            )


def _scenario_summary(
    *,
    name: str,
    output_path: Path,
    output_sha256: str,
    rows: list[tuple[SourceRide, bool]],
    source: dict[str, Any],
    pricing_rules: dict[str, Any],
    expected_winner: str,
) -> dict[str, Any]:
    target_rides = [ride for ride, target in rows if target]
    costs = calculate_costs(target_rides, pricing_rules)
    actual_winner = min(costs, key=lambda option: Decimal(costs[option]))

    if actual_winner != expected_winner:
        raise Part4DataError(
            f"{name} acceptance invariant failed: expected {expected_winner}, "
            f"computed {actual_winner}"
        )

    total_classic = sum(ride.kind == "classic" for ride, _ in rows)
    total_ebike = sum(ride.kind == "ebike" for ride, _ in rows)
    target_classic = sum(ride.kind == "classic" for ride in target_rides)
    target_ebike = sum(ride.kind == "ebike" for ride in target_rides)
    average_minutes = sum(
        (ride.duration_seconds for ride in target_rides),
        Decimal("0"),
    ) / Decimal("60") / len(target_rides)

    return {
        "scenario": name,
        "csv_file": str(output_path.relative_to(PROJECT_ROOT)),
        "csv_sha256": output_sha256,
        "total_rows": len(rows),
        "target_ride_count": len(target_rides),
        "costed_ride_count": len(target_rides),
        "target_selection_rule": TARGET_SELECTION_RULES[name],
        "date_range": {
            "start": min(ride.started_at for ride, _ in rows).isoformat(),
            "end": max(ride.started_at for ride, _ in rows).isoformat(),
        },
        "all_rows": {
            "classic_count": total_classic,
            "ebike_count": total_ebike,
            "unknown_count": len(rows) - total_classic - total_ebike,
        },
        "target_rows": {
            "classic_count": target_classic,
            "ebike_count": target_ebike,
            "minimum_duration_seconds": str(
                min(ride.duration_seconds for ride in target_rides)
            ),
            "maximum_duration_seconds": str(
                max(ride.duration_seconds for ride in target_rides)
            ),
            "average_duration_minutes": str(
                average_minutes.quantize(
                    Decimal("0.001"),
                    rounding=ROUND_HALF_UP,
                )
            ),
        },
        "source_archive": source["url"],
        "source_sha256": source["sha256"],
        "acceptance_costs_usd": costs,
        "expected_winning_option": expected_winner,
    }


def select_scenario_targets(
    rides: list[SourceRide],
) -> dict[str, list[SourceRide]]:
    membership_eligible = [
        ride
        for ride in rides
        if ride.kind == "classic"
        and is_classic_bike_source_row(ride.row)
        and MEMBERSHIP_MIN_DURATION_SECONDS
        <= ride.duration_seconds
        <= MEMBERSHIP_MAX_DURATION_SECONDS
    ]
    pay_per_use_eligible = [
        ride
        for ride in rides
        if ride.kind == "classic"
        and is_classic_bike_source_row(ride.row)
        and PAY_PER_USE_MIN_DURATION_SECONDS
        <= ride.duration_seconds
        <= PAY_PER_USE_MAX_DURATION_SECONDS
    ]

    if len(membership_eligible) < HIGH_TARGET_COUNT:
        raise Part4DataError(
            "source scan found only "
            f"{len(membership_eligible)} Classic rides between 60 and "
            f"2700 seconds; {HIGH_TARGET_COUNT} are required"
        )

    if len(pay_per_use_eligible) < LOW_TARGET_COUNT:
        raise Part4DataError(
            "source scan found only "
            f"{len(pay_per_use_eligible)} Classic rides between 300 and "
            f"900 seconds; {LOW_TARGET_COUNT} are required"
        )

    return {
        "membership_wins": membership_eligible[:HIGH_TARGET_COUNT],
        "pay_per_use_wins": sorted(
            pay_per_use_eligible,
            key=lambda ride: (
                ride.duration_seconds,
                ride.source_row_number,
            ),
        )[:LOW_TARGET_COUNT],
    }


TARGET_SELECTION_RULES: dict[str, dict[str, Any]] = {
    "membership_wins": {
        "required_ride_kind": "classic_bike",
        "minimum_duration_seconds": int(MEMBERSHIP_MIN_DURATION_SECONDS),
        "maximum_duration_seconds": int(MEMBERSHIP_MAX_DURATION_SECONDS),
        "bounds_inclusive": True,
        "target_count": HIGH_TARGET_COUNT,
        "selection_order": "first qualifying rows in source archive order",
    },
    "pay_per_use_wins": {
        "required_ride_kind": "classic_bike",
        "minimum_duration_seconds": int(PAY_PER_USE_MIN_DURATION_SECONDS),
        "maximum_duration_seconds": int(PAY_PER_USE_MAX_DURATION_SECONDS),
        "bounds_inclusive": True,
        "target_count": LOW_TARGET_COUNT,
        "selection_order": (
            "shortest duration first; equal-duration ties use source row order"
        ),
    },
}


def generate_scenarios(
    *,
    archive_path: Path,
    archive_metadata: dict[str, Any],
    snapshot_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if _sha256(archive_path) != archive_metadata["sha256"]:
        raise Part4DataError("source archive SHA-256 does not match metadata")

    if not verify_snapshot_hash(snapshot_path):
        raise Part4DataError("pricing snapshot HTML SHA-256 mismatch")

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    pricing_rules = snapshot["pricing_rules"]
    member, fieldnames, rides, scanned = load_source_rides(archive_path)
    target_sets = select_scenario_targets(rides)
    scenarios = [
        (
            "membership_wins",
            target_sets["membership_wins"],
            "membership",
            (
                "first 40 Classic-bike rows between 60 and 2700 seconds "
                "inclusive, in source archive order"
            ),
        ),
        (
            "pay_per_use_wins",
            target_sets["pay_per_use_wins"],
            "pay_per_use",
            (
                "two shortest Classic-bike rows between 300 and 900 seconds "
                "inclusive; equal-duration ties use source row order"
            ),
        ),
    ]
    summaries = []
    selection_rules = {}

    for name, targets, winner, selection_rule in scenarios:
        rows = _scenario_rows(rides, targets)
        output_path = output_dir / f"{name}.csv"
        output_hash = _write_scenario_csv(output_path, fieldnames, rows)
        summaries.append(
            _scenario_summary(
                name=name,
                output_path=output_path,
                output_sha256=output_hash,
                rows=rows,
                source=archive_metadata,
                pricing_rules=pricing_rules,
                expected_winner=winner,
            )
        )
        selection_rules[name] = selection_rule

    is_official = (
        archive_metadata.get("data_classification")
        == "official_public_archive"
    )
    disclosure = (
        "All trip rows come from the official archive. Only the "
        "scenario_target assignment is synthetic."
        if is_official
        else (
            "TEST-ONLY: source rows are synthetic fixture rows and must not "
            "be represented as official trip data."
        )
    )
    manifest = {
        "source": {
            **archive_metadata,
            "archive_member": member,
            "rows_scanned": scanned,
        },
        "policy_snapshot": {
            "file": str(snapshot_path.relative_to(PROJECT_ROOT)),
            "final_url": snapshot["final_url"],
            "html_sha256": snapshot["html_sha256"],
            "pricing_rules": pricing_rules,
        },
        "transformation": {
            "output_rows_per_scenario": SCENARIO_ROW_COUNT,
            "preserved_fields": fieldnames,
            "added_fields": ["scenario_target"],
            "selection_rules": selection_rules,
            "target_row_quality_rules": TARGET_SELECTION_RULES,
            "background_rule": (
                "fill to 600 rows from valid source trips in source order; "
                "background rows are not included in target-user costs"
            ),
            "cost_input_rule": (
                "include only rows where scenario_target is true; exclude "
                "all background rows"
            ),
            "source_fact_rule": (
                "preserve every parsed source-field text value; "
                "add only scenario_target"
            ),
            "scenario_overlay_disclosure": (
                disclosure
            ),
            "cost_assumptions": (
                "Use exact elapsed minutes without rounding each ride; apply "
                "unlock and per-minute rates from the captured pricing "
                "passages; round only final scenario totals to cents."
            ),
        },
        "scenarios": summaries,
    }
    _write_json(output_dir / "transformation_manifest.json", manifest)
    _write_json(output_dir / "scenario_summary.json", {"scenarios": summaries})

    return manifest


def verify_outputs(
    *,
    snapshot_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    if not verify_snapshot_hash(snapshot_path):
        raise Part4DataError("pricing snapshot hash verification failed")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pricing_rules = manifest["policy_snapshot"]["pricing_rules"]
    checks = []

    for scenario in manifest["scenarios"]:
        csv_path = PROJECT_ROOT / scenario["csv_file"]

        with csv_path.open("r", encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            rows = list(reader)

        target_count = sum(row["scenario_target"] == "true" for row in rows)
        target_rides = [
            SourceRide(
                source_row_number=index,
                row=row,
                duration_seconds=ride_duration_seconds(row),
                started_at=ride_start(row),
                kind=ride_kind(row),
            )
            for index, row in enumerate(rows, start=2)
            if row["scenario_target"] == "true"
        ]
        rule = manifest["transformation"]["target_row_quality_rules"][
            scenario["scenario"]
        ]
        minimum_seconds = Decimal(str(rule["minimum_duration_seconds"]))
        maximum_seconds = Decimal(str(rule["maximum_duration_seconds"]))
        target_quality_matches = all(
            is_classic_bike_source_row(ride.row)
            and minimum_seconds
            <= ride.duration_seconds
            <= maximum_seconds
            for ride in target_rides
        )
        costs = calculate_costs(target_rides, pricing_rules)
        winner = min(costs, key=lambda option: Decimal(costs[option]))
        checks.append(
            {
                "scenario": scenario["scenario"],
                "row_count": len(rows),
                "target_count": target_count,
                "hash_matches": _sha256(csv_path) == scenario["csv_sha256"],
                "row_count_matches": len(rows)
                == scenario["total_rows"]
                == SCENARIO_ROW_COUNT,
                "source_fields_unchanged": reader.fieldnames
                == [
                    *manifest["transformation"]["preserved_fields"],
                    "scenario_target",
                ],
                "target_count_matches": target_count
                == scenario["target_ride_count"]
                == scenario["costed_ride_count"]
                == rule["target_count"],
                "target_quality_matches": target_quality_matches,
                "target_rule_matches": scenario["target_selection_rule"]
                == rule,
                "costs_match": costs == scenario["acceptance_costs_usd"],
                "winner": winner,
                "winner_matches": winner
                == scenario["expected_winning_option"],
            }
        )

    if not all(
        check["hash_matches"]
        and check["row_count_matches"]
        and check["source_fields_unchanged"]
        and check["target_count_matches"]
        and check["target_quality_matches"]
        and check["target_rule_matches"]
        and check["costs_match"]
        and check["winner_matches"]
        for check in checks
    ):
        raise Part4DataError("one or more generated scenario checks failed")

    return {
        "snapshot_hash_matches": True,
        "scenarios": checks,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare and verify HW7 Part 4 official public data.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("capture-policy")
    download = subparsers.add_parser("download-archive")
    download.add_argument("--url", default=DEFAULT_ARCHIVE_URL)
    download.add_argument("--month", default=DEFAULT_ARCHIVE_MONTH)
    generate = subparsers.add_parser("generate-scenarios")
    generate.add_argument("--url", default=DEFAULT_ARCHIVE_URL)
    generate.add_argument("--month", default=DEFAULT_ARCHIVE_MONTH)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--url", default=DEFAULT_ARCHIVE_URL)
    prepare.add_argument("--month", default=DEFAULT_ARCHIVE_MONTH)
    subparsers.add_parser("verify")

    return parser.parse_args()


def _archive_path_for_month(month: str) -> Path:
    if month != DEFAULT_ARCHIVE_MONTH:
        raise Part4DataError(
            f"month must be the pinned value {DEFAULT_ARCHIVE_MONTH}"
        )

    return DEFAULT_ARCHIVE_PATH


def main() -> None:
    args = parse_args()

    if args.command in {"capture-policy", "prepare"}:
        snapshot = capture_policy_snapshot(
            url=PRICING_URL,
            html_path=DEFAULT_HTML_PATH,
            snapshot_path=DEFAULT_SNAPSHOT_PATH,
        )
        print(
            "POLICY_CAPTURED "
            f"final_url={snapshot['final_url']} "
            f"bytes={snapshot['html_bytes']} "
            f"sha256={snapshot['html_sha256']}"
        )

        if args.command == "capture-policy":
            return

    if args.command in {"download-archive", "prepare"}:
        archive_path = _archive_path_for_month(args.month)
        archive = download_archive(
            url=args.url,
            month=args.month,
            destination=archive_path,
        )
        _write_json(DEFAULT_CACHE_DIR / "archive_metadata.json", archive)
        print(
            "ARCHIVE_DOWNLOADED "
            f"month={archive['month']} bytes={archive['bytes']} "
            f"sha256={archive['sha256']}"
        )

        if args.command == "download-archive":
            return

    if args.command in {"generate-scenarios", "prepare"}:
        archive_path = _archive_path_for_month(args.month)
        metadata_path = DEFAULT_CACHE_DIR / "archive_metadata.json"

        if not metadata_path.exists():
            raise Part4DataError(
                "archive metadata is missing; run download-archive first"
            )

        archive = json.loads(metadata_path.read_text(encoding="utf-8"))

        if (
            archive.get("data_classification") != "official_public_archive"
            or archive.get("url") != args.url
            or archive.get("month") != args.month
        ):
            raise Part4DataError(
                "archive metadata does not match the requested official "
                "URL and month"
            )

        manifest = generate_scenarios(
            archive_path=archive_path,
            archive_metadata=archive,
            snapshot_path=DEFAULT_SNAPSHOT_PATH,
            output_dir=SCENARIO_DIR,
        )
        print(
            "SCENARIOS_GENERATED "
            + ", ".join(
                f"{item['scenario']}={item['total_rows']} rows/"
                f"{item['target_ride_count']} targets/"
                f"winner:{item['expected_winning_option']}"
                for item in manifest["scenarios"]
            )
        )
        return

    verification = verify_outputs(
        snapshot_path=DEFAULT_SNAPSHOT_PATH,
        manifest_path=DEFAULT_MANIFEST_PATH,
    )
    print(json.dumps(verification, indent=2))


if __name__ == "__main__":
    main()
