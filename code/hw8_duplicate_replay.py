"""Replay one CREATE_LISTING request to measure duplicate side effects."""

import argparse
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from hw8_config import PORT_BASE, RESPONSE_TOPIC

API_URL = os.getenv(
    "HW8_API_URL",
    f"http://127.0.0.1:{PORT_BASE}/hw8/listings",
)


def parse_args() -> argparse.Namespace:
    """Parse the evidence label and output path."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--label",
        choices=("before_fix", "after_fix"),
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def post_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Send one HTTP request through FastAPI and Kafka."""

    response = requests.post(API_URL, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def run(label: str) -> dict[str, Any]:
    """Send the exact same correlated create request twice."""

    correlation_id = str(uuid4())
    request = {
        "correlation_id": correlation_id,
        "reply_to": RESPONSE_TOPIC,
        "operation": "CREATE_LISTING",
        "data": {
            "listingTitle": "Duplicate Replay Test Listing",
            "address": "2974 Replay Avenue, San Jose, CA",
            "description": (
                "A deterministic listing used to test duplicate Kafka delivery."
            ),
            "propertyType": "Apartment",
            "monthlyRent": 2297,
            "availableUnits": 1,
        },
    }

    print("[DUPLICATE TEST] Sending original request", flush=True)
    print(json.dumps(request, indent=2, sort_keys=True), flush=True)
    first_response = post_request(request)
    print("[DUPLICATE TEST] First response", flush=True)
    print(json.dumps(first_response, indent=2, sort_keys=True), flush=True)

    print("[DUPLICATE TEST] Replaying identical correlation_id", flush=True)
    second_response = post_request(request)
    print("[DUPLICATE TEST] Second response", flush=True)
    print(json.dumps(second_response, indent=2, sort_keys=True), flush=True)

    first_entity_id = first_response.get("entity_id")
    second_entity_id = second_response.get("entity_id")
    result = {
        "scenario": "duplicate_delivery",
        "label": label,
        "correlation_id": correlation_id,
        "same_correlation_id": (
            first_response.get("correlation_id")
            == second_response.get("correlation_id")
            == correlation_id
        ),
        "first_entity_id": first_entity_id,
        "second_entity_id": second_entity_id,
        "same_entity_id": first_entity_id == second_entity_id,
        "extra_side_effect": first_entity_id != second_entity_id,
        "first_response": first_response,
        "second_response": second_response,
    }
    print("[DUPLICATE TEST] Summary", flush=True)
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return result


def main() -> None:
    """Run the replay and save machine-readable evidence."""

    args = parse_args()
    result = run(args.label)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[DUPLICATE TEST] Wrote {args.output}", flush=True)


if __name__ == "__main__":
    main()
