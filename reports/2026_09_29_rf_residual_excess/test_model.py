import copy
import unittest

from model import Evidence


def example():
    rows = []
    for group, end in (("a", 1), ("b", 2)):
        for rf, base in ((100, 10.0), (200, 20.0)):
            for number in (1, 2, 3):
                rows.append(
                    dict(
                        unit_id=group,
                        available_utc_ns=end,
                        receiver_id=0,
                        rf_hz=rf,
                        number=number,
                        session_id=group,
                        track_id=f"{rf}-{number}",
                        shape=dict(slope=base + (2 if number == 1 else 0)),
                    )
                )
    target = dict(receiver_id=0, rf_hz=200, number=1, start_utc_ns=3)
    return rows, target


class Tests(unittest.TestCase):
    def test_excess_and_shuffle(self):
        rows, t = example()
        p = Evidence(rows).predict(t)
        s = Evidence(rows, True).predict(t)
        self.assertEqual(p["rf_slope"], 20.0)
        self.assertEqual(p["excess_slope"], 2.0)
        self.assertEqual(p["total_slope"], 22.0)
        self.assertNotEqual(p["total_slope"], s["total_slope"])

    def test_future_and_receiver(self):
        rows, t = example()
        t["start_utc_ns"] = 2
        self.assertIsNone(Evidence(rows).predict(t))
        t["start_utc_ns"] = 3
        t["receiver_id"] = 1
        self.assertIsNone(Evidence(rows).predict(t))

    def test_no_held_dependence_and_order(self):
        rows, t = example()
        before = Evidence(rows, True).predict(t)
        t["held_residual"] = [99999]
        changed = copy.deepcopy(rows)
        for row in changed:
            row["held_score"] = -999999
        self.assertEqual(Evidence(list(reversed(changed)), True).predict(t), before)

    def test_need_other_candidates(self):
        rows, t = example()
        rows = [r for r in rows if r["number"] != 3]
        self.assertIsNone(Evidence(rows).predict(t))


if __name__ == "__main__":
    unittest.main()
