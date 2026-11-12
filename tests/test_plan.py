import unittest
from planning import work_plan


class PlanningTests(unittest.TestCase):
    def test_payout_dates_and_conditional_licenses(self):
        bills = [{"state": "open", "due": "2026-11-20", "cents": 8000}]

        def item(key, day, reward, minutes=5):
            return {
                "id": key,
                "payday": day,
                "reward": reward,
                "kind": "choice",
                "minutes": minutes,
            }

        items = [
            item("a", "2026-11-19", 2000),
            item("b", "2026-11-20", 1000),
            item("later", "2026-12-02", 4000),
            item("photo", None, None),
        ]
        result = work_plan(bills, 5000, [{"jobs": items}], {})
        self.assertEqual(
            (result["ids"], result["remaining"], result["minutes"]), (["a", "b"], 0, 10)
        )
        result = work_plan(bills, 5000, [{"jobs": items}], {"a": {"state": "received"}})
        self.assertEqual((result["ids"], result["remaining"]), (["b"], 2000))
        self.assertIsNone(work_plan(bills, 8500, [{"jobs": items}], {}))
