import unittest
from evaluate import relation


class RelationTests(unittest.TestCase):
    def test_known_relation_and_validation_isolation(self):
        rows=[dict(orbit=x,phase=.03-.8*x) for x in (.1,.13,.17,.2,.24,.3)]
        result=relation(rows,rows)
        self.assertTrue(result['passed'])
        self.assertAlmostEqual(result['beta'],-.8,places=8)
        changed=relation(rows,[dict(r,phase=r['phase']+1) for r in rows])
        self.assertEqual(result['beta'],changed['beta'])
        self.assertEqual(result['intercept'],changed['intercept'])
        self.assertFalse(changed['passed'])

    def test_rank_failure_is_explicit(self):
        rows=[dict(orbit=.1,phase=float(i)) for i in range(6)]
        result=relation(rows,rows)
        self.assertFalse(result['qualified'])
        self.assertEqual(result['reason'],'insufficient_source_groups_or_rank')
