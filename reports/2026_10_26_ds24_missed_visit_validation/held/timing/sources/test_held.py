import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
import held


class HeldApplicationTests(unittest.TestCase):
    def test_shared_samples_r01_selection_precedes_fullwindow_controls(self):
        support=dict(start_counter=1,stop_counter=11);one=dict(header={'prediction_id':'p'},target_support=support)
        two=dict(prediction_id='p',target_support=copy.deepcopy(support));events=[];source=np.arange(10,dtype=complex)
        def first(values,rate,edge,packet,callback):
            self.assertTrue(np.shares_memory(source,values));callback({'selection':True});events.append('r01_complete')
            return dict(owner_id='o',status='complete')
        def second(values,rate,edge,packet):
            self.assertTrue(np.shares_memory(source,values));events.append('r02_fullwindow');return dict(owner_id='o',operational_admitted=False)
        engines=(SimpleNamespace(score_target=first),SimpleNamespace(adapt=lambda p,a:{}),SimpleNamespace(score_packet=second))
        with patch.object(held,'engines',return_value=engines):
            r=held.score_receiver(source,10_000_000,'lower',one,two,{},lambda value:events.append('selection_sealed'))
        self.assertEqual(events,['selection_sealed','r01_complete','r02_fullwindow'])
        self.assertFalse(r['best_method_selected']);self.assertFalse(r['r02']['operational_admitted'])

    def test_support_mismatch_rejected_before_scoring(self):
        one=dict(header={'prediction_id':'p'},target_support={'start_counter':1,'stop_counter':11})
        two=dict(prediction_id='p',target_support={'start_counter':2,'stop_counter':12})
        with self.assertRaisesRegex(ValueError,'supports differ'):
            held.score_receiver(np.zeros(10),10_000_000,'lower',one,two,{},lambda value:None)


if __name__=='__main__':unittest.main(verbosity=2)
