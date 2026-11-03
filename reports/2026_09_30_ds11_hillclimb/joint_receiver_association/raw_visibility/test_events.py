import unittest
from events import event


class EventTests(unittest.TestCase):
    def test_duplicate_anchor_and_order_invariance(self):
        a=dict(id='a',receiver=0,epoch_us=10.)
        b=dict(id='b',receiver=1,epoch_us=10.01)
        args=([[a],[b]],{'a':{1}},1,.03,1000.)
        out=event([a],*args)
        self.assertTrue(out['hit']);self.assertTrue(out['raw_only'])
        self.assertEqual(out,event([a,a],*args))
        out=event([a],[[a],[b]],{'a':{1},'b':{2}},1,.03,1000.)
        self.assertTrue(out['conflicting_inferred_partner'])
        self.assertFalse(out['raw_only'])
