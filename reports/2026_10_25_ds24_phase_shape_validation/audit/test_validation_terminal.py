"""Fixture-only terminal audit ownership and original endpoint predicates."""
from types import SimpleNamespace
import unittest
import numpy as np
import validation_terminal as a


class TerminalTests(unittest.TestCase):
    def test_endpoint_predicate_rejects_nonfinite_and_outside_box(self):
        self.assertTrue(a.endpoint_in_box(dict(endpoint_east_north_km=[12.5,-12.5])))
        self.assertFalse(a.endpoint_in_box(dict(endpoint_east_north_km=[12.5001,0.])))
        self.assertFalse(a.endpoint_in_box(dict(endpoint_east_north_km=[float('nan'),0.])))

    def test_original_gate_map_retains_failure_and_empty_prediction(self):
        saved=dict(gates=dict(tracks=[dict(component='a',compatible=True),dict(component='b',compatible=False)]))
        self.assertEqual(a.gate_map(saved),dict(curved={'a':True,'b':False},predictive={}))

    def test_likelihood_detects_native_overlap_and_exact_unique_counts(self):
        tracks=[dict(observation_ids=['a','b']),dict(observation_ids=['c','d'])]
        d=dict(scan=SimpleNamespace(tracks=tracks),entries=[dict(track_index=1)],
               observations=[dict(observation_id=x) for x in ['a','b','c','d']])
        p=SimpleNamespace(members=[0],slices=[slice(0,2)],keep=np.array([True,False]))
        counts,ok=a.likelihood(d,p)
        self.assertTrue(ok);self.assertEqual(counts['curved_unique'],1)
        self.assertEqual(counts['predictive_unique'],2);self.assertEqual(counts['union_unique'],3)
        d['entries'][0]['observation_ids']=['a','d']
        self.assertFalse(a.likelihood(d,p)[1])


if __name__=='__main__':unittest.main()
