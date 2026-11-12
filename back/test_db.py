
import unittest
from datetime import date

from app.services.plan_rules import (
    get_plan_days,
    distribute_numeric_target,
)


class TestPlanRules(unittest.TestCase):

    def test_inclusive_dates(self):
        days = get_plan_days(
            date(2026, 11, 1),
            date(2026, 11, 3),
        )

        self.assertEqual(len(days), 3)

    def test_numeric_distribution(self):
        result = distribute_numeric_target(
            100,
            date(2026, 11, 1),
            date(2026, 11, 3),
        )

        self.assertEqual(
            list(result.values()),
            [33, 33, 34],
        )

    def test_invalid_dates(self):
        with self.assertRaises(ValueError):
            get_plan_days(
                date(2026, 11, 3),
                date(2026, 11, 1),
            )

    def test_invalid_quantity(self):
        with self.assertRaises(ValueError):
            distribute_numeric_target(
                -10,
                date(2026, 11, 1),
                date(2026, 11, 3),
            )


if __name__ == "__main__":
    unittest.main()
