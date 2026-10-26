import unittest
from audit import BIN,decision,digest,summary


class AuditTests(unittest.TestCase):
    def test_pilot_is_separate_from_continuity(self):
        score=dict(status='complete',tracking_cfo_hz=1000+BIN,margin=.025)
        result=decision(score,dict(cfo_hz=1000,cfo_half_width_hz=100))
        self.assertTrue(result['pilot']);self.assertFalse(result['compatible']);self.assertFalse(result['admitted'])
        self.assertFalse(result['zero_bin'])

    def test_additions_retain_originals_and_keep_methods_separate(self):
        failed=decision(None,{})
        rows=[dict(original=True,unavailable=False,methods={'one':failed}),
            dict(original=False,unavailable=False,methods={'one':dict(pilot=True,compatible=True,admitted=True,zero_bin=True)})]
        result=summary(rows,'one')
        self.assertEqual(result['new'],1);self.assertEqual(result['lost_if_replacement'],1)
        self.assertEqual(result['original_lost_additions_only'],0)
        self.assertEqual(result['new_zero_bin'],1)

    def test_receipt_digest_is_order_invariant_and_value_sensitive(self):
        self.assertEqual(digest(dict(a=1,b=2)),digest(dict(b=2,a=1)))
        self.assertNotEqual(digest(dict(a=1)),digest(dict(a=2)))


if __name__=='__main__':unittest.main()
