import unittest
from run import select,gate

class SelectionTests(unittest.TestCase):
    def test_training_selection_excludes_failed_wrong_arm_and_scan(self):
        def attempt(score,qualified=True,exit_code=0,index=0,arm='orbit'):
            return dict(job=dict(index=index,arm=arm),receipt=dict(exit_code=exit_code),
                        result=dict(endpoint=dict(score=score,qualified=qualified)))
        attempts=[attempt(1),attempt(2),attempt(100,qualified=False),attempt(101,exit_code=124),
                  attempt(102,index=16),attempt(103,arm='linear')]
        self.assertEqual(select(attempts,0,'orbit')['score'],2)
        self.assertIsNone(select(attempts,3,'orbit'))

    def test_gate_requires_every_control_and_scan(self):
        a=dict(errors_m=dict(iid=10,zero=9,linear=8,orbit=7))
        self.assertTrue(gate([a,a]))
        for errors in (dict(iid=6,zero=9,linear=8,orbit=7),dict(iid=10,zero=None,linear=8,orbit=7),
                       dict(iid=10,zero=9,linear=7,orbit=7)):
            self.assertFalse(gate([a,dict(errors_m=errors)]))
        self.assertFalse(gate([]))
