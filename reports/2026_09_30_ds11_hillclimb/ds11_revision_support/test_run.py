import unittest
from types import SimpleNamespace
from run import common_support,historical,original_ref
class SupportTests(unittest.TestCase):
    def test_repeated_digest_retains_exact_occurrence(self):
        refs=[SimpleNamespace(digest='same',provider='p',collected_utc_ns=t) for t in (1,10)]
        self.assertEqual(original_ref(refs,'same',dict(provider='p',collected_utc_ns=1)).collected_utc_ns,1)
        with self.assertRaises(AssertionError):original_ref(refs,'same',dict(provider='p',collected_utc_ns=3))
    def test_strict_and_inclusive_snapshot_cutoff(self):
        refs=[SimpleNamespace(collected_utc_ns=t,sha256=str(t)) for t in (1,2,3)]
        self.assertEqual(historical.select(refs,3).collected_utc_ns,2)
        self.assertEqual(historical.select(refs,3,False).collected_utc_ns,3)
        self.assertIsNone(historical.select(refs,1))
    def test_common_identity_and_missing_selected_rejected(self):
        mapping={'a':dict(candidate_norad=[1,2,3]),'b':dict(candidate_norad=[2,3,4])}
        g=dict(track_ids=['a','b'],norad=2,common_candidate_norads=2)
        self.assertEqual(common_support(g,mapping),[2,3])
        with self.assertRaises(AssertionError):common_support(dict(g,norad=1),mapping)
