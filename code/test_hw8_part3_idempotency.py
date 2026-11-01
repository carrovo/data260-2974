"""Deterministic offline tests for HW8 duplicate-delivery handling."""

import unittest

from hw8_config import RESPONSE_TOPIC
from hw8_messages import process_request_idempotently

ENTITY_ID = "00000000-0000-0000-0000-000000002974"


def create_request(monthly_rent: int = 2297) -> dict[str, object]:
    """Build one valid correlated CREATE_LISTING request."""

    return {
        "correlation_id": "duplicate-correlation-2974",
        "reply_to": RESPONSE_TOPIC,
        "operation": "CREATE_LISTING",
        "data": {
            "listingTitle": "Duplicate Replay Test Listing",
            "address": "2974 Replay Avenue, San Jose, CA",
            "description": (
                "A deterministic listing used to test duplicate Kafka delivery."
            ),
            "propertyType": "Apartment",
            "monthlyRent": monthly_rent,
            "availableUnits": 1,
        },
    }


class IdempotencyTests(unittest.TestCase):
    """Verify exact replay suppression and conflicting-key rejection."""

    def setUp(self) -> None:
        self.entities: dict[str, dict[str, object]] = {}
        self.cache: dict[str, dict[str, object]] = {}

    def test_exact_replay_returns_same_entity_without_side_effect(self) -> None:
        request = create_request()
        first = process_request_idempotently(
            request,
            self.entities,
            self.cache,
            id_factory=lambda: ENTITY_ID,
        )
        second = process_request_idempotently(
            request,
            self.entities,
            self.cache,
            id_factory=lambda: "must-not-be-created",
        )

        self.assertEqual(first["entity_id"], ENTITY_ID)
        self.assertEqual(second["entity_id"], ENTITY_ID)
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(len(self.entities), 1)
        self.assertEqual(len(self.cache), 1)

    def test_same_correlation_with_different_data_is_rejected(self) -> None:
        process_request_idempotently(
            create_request(monthly_rent=2297),
            self.entities,
            self.cache,
            id_factory=lambda: ENTITY_ID,
        )
        conflicting = process_request_idempotently(
            create_request(monthly_rent=9999),
            self.entities,
            self.cache,
        )

        self.assertFalse(conflicting["success"])
        self.assertEqual(
            conflicting["error"],
            "correlation_id reused with different request",
        )
        self.assertEqual(len(self.entities), 1)


if __name__ == "__main__":
    unittest.main()
