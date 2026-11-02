"""Offline tests for the controlled consumer-death processing delay."""

import unittest

from hw8_agent_logic import processing_delay_seconds


class ConsumerDeathDelayTests(unittest.TestCase):
    """Verify failure-test delay parsing and bounds."""

    def test_missing_delay_defaults_to_zero(self) -> None:
        self.assertEqual(processing_delay_seconds({}), 0)

    def test_numeric_delay_is_accepted(self) -> None:
        self.assertEqual(
            processing_delay_seconds({"processing_delay_seconds": 45}),
            45,
        )

    def test_boolean_delay_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be numeric"):
            processing_delay_seconds({"processing_delay_seconds": True})

    def test_out_of_range_delay_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 120"):
            processing_delay_seconds({"processing_delay_seconds": 121})


if __name__ == "__main__":
    unittest.main()
