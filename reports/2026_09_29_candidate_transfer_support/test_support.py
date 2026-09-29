import unittest

from support import census


def scan(sid, time, panel="DS7_early_8", snapshot="a", weight=1.0, receiver="rx0"):
    return dict(
        session_id=sid,
        start_utc_ns=time,
        panel=panel,
        snapshot=snapshot,
        catalogue_size=10,
        tracks=[
            dict(
                track_id=sid,
                ids=[3, 4],
                weights=[weight, 1 - weight],
                signal_responsibility=1.0,
                receiver_id=receiver,
                rf_hz=100,
            )
        ],
    )


class Tests(unittest.TestCase):
    def row(self, scans, scope="any_earlier_scan", match="any_receiver_rf"):
        return next(
            r
            for r in census(scans)
            if r["session_id"] == "target" and r["scope"] == scope and r["match"] == match
        )

    def test_two_distinct_past_records(self):
        ss = [scan("a", 1), scan("b", 2), scan("target", 3)]
        self.assertEqual(self.row(ss)["strong_two_scan_mass"], 1.0)
        self.assertEqual(self.row(ss[:1] + ss[2:])["strong_two_scan_mass"], 0.0)

    def test_future_and_simultaneous_do_not_count(self):
        ss = [scan("a", 3), scan("b", 4), scan("target", 3)]
        self.assertEqual(self.row(ss)["raw_two_scan_mass"], 0.0)

    def test_snapshot_row_collision(self):
        ss = [scan("a", 1, snapshot="b"), scan("b", 2, snapshot="b"), scan("target", 3)]
        self.assertEqual(self.row(ss)["raw_two_scan_mass"], 0.0)

    def test_panel_and_receiver_isolation(self):
        ss = [scan("a", 1, receiver="rx1"), scan("b", 2, receiver="rx1"), scan("target", 3)]
        self.assertEqual(self.row(ss, "earlier_other_panel")["strong_two_scan_mass"], 0.0)
        self.assertEqual(self.row(ss, match="same_receiver_rf")["strong_two_scan_mass"], 0.0)

    def test_weak_donors_and_background(self):
        ss = [scan("a", 1, weight=0.4), scan("b", 2, weight=0.4), scan("target", 3)]
        self.assertEqual(self.row(ss)["raw_two_scan_mass"], 1.0)
        self.assertEqual(self.row(ss)["strong_two_scan_mass"], 0.0)
        for s in ss[:2]:
            s["tracks"][0]["signal_responsibility"] = 0.1
        self.assertEqual(self.row(ss)["strong_two_scan_mass"], 0.0)

    def test_duplicate_record_rejected(self):
        with self.assertRaises(ValueError):
            census([scan("a", 1), scan("a", 2)])


if __name__ == "__main__":
    unittest.main()
