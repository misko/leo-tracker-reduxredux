import copy
import unittest

from features import build, training


class Tests(unittest.TestCase):
    def setUp(self):
        self.session = "synthetic"
        self.train = [v for v in range(100) if training(self.session, v)][:2]
        self.held = next(v for v in range(100) if not training(self.session, v))
        self.probes = [dict(receiver=0, rf_hz=100, visit_index=v, passing=passing)
                       for v, passing in ((self.train[0], 1), (self.train[1], 0), (self.held, 1))]
        self.tracks = [dict(track_id="x", receiver_id=0, rf_hz=100,
                           visits=[self.train[0]], training_mask=[True])]

    def test_exact_lane(self):
        extras = [dict(receiver=1, rf_hz=100, visit_index=self.train[0], passing=0),
                  dict(receiver=0, rf_hz=100.1, visit_index=self.train[0], passing=0)]
        r = build(self.session, self.probes + extras, self.tracks)[0]
        self.assertEqual((r["training_probes"], r["training_empty"]), (2, 1))
        self.assertEqual(r["empty_logit"], 0)

    def test_held_isolation(self):
        changed = copy.deepcopy(self.probes)
        changed[-1]["passing"] = 1000
        self.assertEqual(build(self.session, self.probes, self.tracks),
                         build(self.session, changed, self.tracks))

    def test_missing_and_partition(self):
        with self.assertRaises(ValueError):
            build(self.session, self.probes[1:], self.tracks)
        self.tracks[0]["training_mask"] = [False]
        with self.assertRaises(ValueError):
            build(self.session, self.probes, self.tracks)
