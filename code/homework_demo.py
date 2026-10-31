"""Demonstrate CREATE_LISTING followed by GET_LISTING through Kafka."""

import json
import os
from typing import Any
from uuid import uuid4

import requests

from hw8_config import PORT_BASE, RESPONSE_TOPIC

API_URL = os.getenv(
    "HW8_API_URL",
    f"http://127.0.0.1:{PORT_BASE}/hw8/listings",
)


def show(label: str, value: object) -> None:
    """Print labeled JSON for the required demonstration evidence."""

    print(f"\n{label}")
    print(json.dumps(value, indent=2, sort_keys=True))


def post_operation(request: dict[str, Any]) -> dict[str, Any]:
    """Post one operation to FastAPI and return its JSON response."""

    response = requests.post(API_URL, json=request, timeout=20)
    response.raise_for_status()
    return response.json()


def main() -> None:
    """Run and verify the complete CREATE_LISTING to GET_LISTING sequence."""

    create_correlation_id = str(uuid4())
    create_request = {
        "correlation_id": create_correlation_id,
        "reply_to": RESPONSE_TOPIC,
        "operation": "CREATE_LISTING",
        "data": {
            "listingTitle": "Studio Near SJSU",
            "address": "100 Example Street, San Jose, CA",
            "description": "A furnished studio located close to the SJSU campus.",
            "propertyType": "Studio",
            "monthlyRent": 1800,
            "availableUnits": 1,
        },
    }
    show("[CLIENT] CREATE_LISTING REQUEST", create_request)
    create_response = post_operation(create_request)
    show("[CLIENT] CREATE_LISTING RESPONSE", create_response)

    assert create_response["success"] is True
    assert create_response["correlation_id"] == create_correlation_id
    entity_id = create_response["entity_id"]
    print(f"[CLIENT] Extracted entity_id={entity_id}")

    get_correlation_id = str(uuid4())
    get_request = {
        "correlation_id": get_correlation_id,
        "reply_to": RESPONSE_TOPIC,
        "operation": "GET_LISTING",
        "data": {"entity_id": entity_id},
    }
    show("[CLIENT] GET_LISTING REQUEST", get_request)
    get_response = post_operation(get_request)
    show("[CLIENT] GET_LISTING RESPONSE", get_response)

    assert get_response["success"] is True
    assert get_response["correlation_id"] == get_correlation_id
    assert get_response["entity"]["entity_id"] == entity_id

    show("[CLIENT] RETRIEVED RENTAL LISTING", get_response["entity"])
    print("\n[CLIENT] PASS: CREATE_LISTING -> GET_LISTING completed")
    print("[CLIENT] PASS: each correlation_id was preserved end to end")


if __name__ == "__main__":
    main()
