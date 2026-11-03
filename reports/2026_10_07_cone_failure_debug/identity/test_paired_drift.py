import unittest
from types import SimpleNamespace as S
import numpy as np
from paired_drift import pairs,huber,circular,PERIOD

def candidate(rank,margin,offset,cfo):return S(candidate_rank=rank,fractional_margin=margin,fractional_epoch_offset_samples=offset,integer_epoch_sample=100,passed_fractional_margin_gate=True,fractional_tracking_cfo_hz=cfo)

class PairTests(unittest.TestCase):
    def test_pair_selection_ignores_frequency_agreement(self):
        probes=[S(visit_index=1,probe_index=2,actual_rf_hz=1e9,receiver_id=rx,channel=1,valid_start_counter=10**16,probe_start_ms=0,candidates=cs) for rx,cs in [(0,[candidate(0,.8,0,100)]),(1,[candidate(0,.7,.1,101),candidate(1,.9,.2,100000)])]]
        source=S(probes=probes,sample_rate_hz=10**7,timing=S(session_start_device_sample_counter=10**16));r=pairs(source,1e-7)
        self.assertEqual(len(r),1);self.assertEqual(r[0]['rank1'],1);self.assertAlmostEqual(r[0]['difference_hz'],99900);self.assertAlmostEqual(r[0]['epoch_difference_ns'],20.)
    def test_alias_representative_invariance(self):
        np.testing.assert_allclose(circular(np.array([10.,20.])+3*PERIOD),[10.,20.],atol=1e-9)
    def test_exact_retained_rank_overrides_raw_margin(self):
        probes=[S(visit_index=1,probe_index=2,actual_rf_hz=1e9,receiver_id=rx,channel=1,valid_start_counter=10**16,probe_start_ms=0,candidates=[candidate(0,.8,0,100),candidate(1,.9,.2,100000)]) for rx in (0,1)]
        source=S(probes=probes,sample_rate_hz=10**7,timing=S(session_start_device_sample_counter=10**16))
        r=pairs(source,1e-7,{(1,2,0):(17,0),(1,2,1):(29,1)})[0]
        self.assertEqual((r['row0'],r['row1'],r['rank0'],r['rank1']),(17,29,0,1))
        self.assertEqual(pairs(source,1e-7,{(1,2,0):(17,7)}),[])
    def test_huber_rejects_influence_without_rejecting_rows(self):
        x=np.ones((21,1));y=np.r_[np.zeros(20),100000.];b=huber(x,y)
        self.assertAlmostEqual(b[0],5.,places=5)

if __name__=='__main__':unittest.main()
