import unittest
import numpy as np
from timing_model import solve


class Engine:
    def __init__(self,target):self.target=target;self.seen=[]
    def evaluate(self,x,gradient):
        self.seen.append(x.copy())
        return -(x[2]-self.target)**2,np.array([123.,-456.,-2*(x[2]-self.target)])


class TimingTests(unittest.TestCase):
    def test_only_timing_changes_and_irrelevant_gradients_do_not_disqualify(self):
        e=Engine(.4);result=solve(e,[.5,-.1])
        self.assertIsNotNone(result['selected'])
        self.assertAlmostEqual(result['selected']['x'][2],.4)
        for x in e.seen:np.testing.assert_array_equal(x[:2],[.5,-.1])

    def test_boundary_solution_retained_but_not_selected(self):
        result=solve(Engine(10),[0,0])
        self.assertIsNone(result['selected'])
        self.assertEqual(len(result['starts']),3)
