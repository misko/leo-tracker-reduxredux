import unittest
from run import summarize_track
class SupportTests(unittest.TestCase):
    def test_interpolation_extrapolation_nearest(self):
        r=summarize_track(dict(times_s=[-1,0,2,5,6,10],training_mask=[False,True,False,True,False,False]))
        self.assertEqual(r['held_inside_training_span'],1)
        self.assertEqual(r['nearest_training_gap_s'],[1,2,1,5])
    def test_no_training_and_unsorted_times(self):
        r=summarize_track(dict(times_s=[3,1],training_mask=[False,False]))
        self.assertEqual(r['held_with_same_track_training'],0)
        r=summarize_track(dict(times_s=[5,2,0],training_mask=[True,False,True]))
        self.assertEqual(r['nearest_training_gap_s'],[2])
