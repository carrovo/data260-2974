"""Deterministic offline tests for the HW8 Part 1 message logic."""

import unittest

from hw8_config import RESPONSE_TOPIC
from hw8_messages import process_request

ENTITY_ID = "00000000-0000-0000-0000-000000002974"


def request(
    operation: str,
    data: dict[str, object],
    correlation_id: str = "test-correlation-2974",
) -> dict[str, object]:
    """Build a valid request envelope for an offline test."""

    return {
        "correlation_id": correlation_id,
        "reply_to": RESPONSE_TOPIC,
        "operation": operation,
        "data": data,
    }


def valid_listing() -> dict[str, object]:
    """Return deterministic valid listing data."""

    return {
        "listingTitle": "Studio Near SJSU",
        "address": "100 Example Street, San Jose, CA",
        "description": "A furnished studio located close to the SJSU campus.",
        "propertyType": "Studio",
        "monthlyRent": 1800,
        "availableUnits": 1,
    }


class Part1MessageTests(unittest.TestCase):
    """Verify successful round trips and required clean error behavior."""

    def setUp(self) -> None:
        self.entities: dict[str, dict[str, object]] = {}

    def test_create_then_get_round_trip(self) -> None:
        create_response = process_request(
            request("CREATE_LISTING", valid_listing()),
            self.entities,
            id_factory=lambda: ENTITY_ID,
        )
        self.assertTrue(create_response["success"])
        self.assertEqual(create_response["entity_id"], ENTITY_ID)
        self.assertEqual(create_response["correlation_id"], "test-correlation-2974")

        get_response = process_request(
            request(
                "GET_LISTING",
                {"entity_id": ENTITY_ID},
                correlation_id="get-correlation-2974",
            ),
            self.entities,
        )
        self.assertTrue(get_response["success"])
        self.assertEqual(get_response["entity"]["entity_id"], ENTITY_ID)
        self.assertEqual(get_response["correlation_id"], "get-correlation-2974")

    def test_missing_required_field_is_rejected(self) -> None:
        listing = valid_listing()
        del listing["address"]
        response = process_request(
            request("CREATE_LISTING", listing),
            self.entities,
        )
        self.assertFalse(response["success"])
        self.assertEqual(response["error"], "address is required")
        self.assertEqual(response["correlation_id"], "test-correlation-2974")

    def test_empty_and_invalid_values_are_rejected(self) -> None:
        invalid_values = (
            ("listingTitle", " "),
            ("description", "too short"),
            ("propertyType", "Castle"),
            ("monthlyRent", 0),
            ("availableUnits", -1),
        )
        for field, value in invalid_values:
            with self.subTest(field=field):
                listing = valid_listing()
                listing[field] = value
                response = process_request(
                    request("CREATE_LISTING", listing),
                    self.entities,
                )
                self.assertFalse(response["success"])
                self.assertIn(field, response["error"])

    def test_unknown_operation_is_rejected(self) -> None:
        response = process_request(
            request("DELETE_LISTING", {}),
            self.entities,
        )
        self.assertEqual(
            response,
            {
                "correlation_id": "test-correlation-2974",
                "success": False,
                "error": "Unknown operation",
            },
        )

    def test_unknown_entity_is_rejected(self) -> None:
        response = process_request(
            request("GET_LISTING", {"entity_id": "missing"}),
            self.entities,
        )
        self.assertFalse(response["success"])
        self.assertEqual(response["error"], "Rental listing not found")

    def test_invalid_envelope_preserves_available_correlation_id(self) -> None:
        response = process_request(
            {
                "correlation_id": "bad-envelope-2974",
                "reply_to": "wrong-topic",
                "operation": "CREATE_LISTING",
                "data": valid_listing(),
            },
            self.entities,
        )
        self.assertFalse(response["success"])
        self.assertEqual(response["correlation_id"], "bad-envelope-2974")
        self.assertIn("reply_to", response["error"])


if __name__ == "__main__":
    unittest.main()
