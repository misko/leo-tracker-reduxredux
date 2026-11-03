import unittest
import numpy as np
from mode_history import track,rank_modes


class ModeHistoryTests(unittest.TestCase):
    def run_case(self,numbers,gain,groups=None,lanes=None,offsets=None):
        gain=np.array(gain,float); n=len(gain)
        return track(np.arange(n)*10.,np.arange(n) if groups is None else np.array(groups),
                     np.zeros(n,int) if lanes is None else np.array(lanes),np.zeros_like(gain),gain,
                     np.array(numbers),np.zeros(len(numbers)) if offsets is None else np.array(offsets),
                     state=False,beam=32,group_cap=32,top_per_row=len(numbers))

    def test_one_global_mode_across_lanes_and_gaps(self):
        h=self.run_case([11,11],[[8,-np.inf],[-np.inf,10],[8,-np.inf]],lanes=[0,1,0])
        self.assertEqual(h.chosen,{11:0})
        self.assertEqual(h.pairs,((0,0),(2,0)))

    def test_catalog_exclusive_not_just_column_exclusive(self):
        h=self.run_case([11,11],[[8,-np.inf],[-np.inf,10]],groups=[1,1])
        self.assertEqual(len(h.pairs),1)

    def test_parallel_satellites_allowed(self):
        h=self.run_case([11,12],[[8,-np.inf],[-np.inf,10]],groups=[1,1])
        self.assertEqual(len(h.pairs),2)

    def test_prior_once_and_can_abstain(self):
        h=self.run_case([11],[[8],[8]],offsets=[2])
        self.assertAlmostEqual(h.score,16-2-.5*np.log(2))
        self.assertFalse(self.run_case([11],[[-1],[-1]]).pairs)

    def test_mixed_lane_probe_rejected(self):
        with self.assertRaises(ValueError): self.run_case([11],[[8],[8]],groups=[1,1],lanes=[0,1])

    def test_independent_ranking_waits_for_track_evidence(self):
        times=np.arange(12.)
        chosen,scores,pairs=rank_modes(times,np.arange(12),np.zeros(12,int),np.zeros((12,2)),
            np.full((12,2),2.),[11,11],np.array([2.,0.]))
        self.assertEqual(chosen,{11:1})
        self.assertEqual(len(pairs),12)
        self.assertAlmostEqual(scores[1]-scores[0],2.)

    def test_independent_short_support_cannot_admit(self):
        chosen,_,pairs=rank_modes(np.arange(9.),np.arange(9),np.zeros(9,int),np.zeros((9,1)),
            np.full((9,1),20.),[11],np.zeros(1))
        self.assertFalse(chosen);self.assertFalse(pairs)


if __name__=='__main__': unittest.main()
