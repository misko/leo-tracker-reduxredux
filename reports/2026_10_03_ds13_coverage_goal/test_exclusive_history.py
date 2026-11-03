import unittest
from exclusive_history import prune


class ExclusiveHistoryTests(unittest.TestCase):
    def test_prune_until_stable_without_readding(self):
        calls=[]
        def decode(active):
            calls.append(active.copy())
            return [(c,c) for c in active]
        def coherent(pairs):
            return pairs[:-1] if len(pairs)>1 else pairs
        active,pairs,trace=prune(3,decode,coherent)
        self.assertEqual(calls,[[0,1,2],[0,1],[0]])
        self.assertEqual(active,[0]);self.assertEqual(pairs,[(0,0)])

    def test_no_support_abstains(self):
        active,pairs,trace=prune(2,lambda a:[],lambda p:p)
        self.assertFalse(active);self.assertFalse(pairs)

    def test_reused_peak_rejected(self):
        with self.assertRaises(ValueError):prune(2,lambda a:[(0,0),(0,1)],lambda p:p)


if __name__=='__main__':unittest.main()
