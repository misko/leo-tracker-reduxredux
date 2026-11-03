import unittest
import numpy as np
from audit_missing_edges import eligible_segment_rows


class MissingEdgeTests(unittest.TestCase):
    def test_keeps_competing_peaks_but_not_other_lanes_or_outside_segment(self):
        segment={'receiver':0,'channel':1,'start_s':10.,'end_s':20.}
        rows=eligible_segment_rows(segment,np.arange(6),np.array([10,10,15,21,16,17]),
             np.array([0,0,1,0,0,0]),np.array([1,1,1,1,1,1]),
             np.array([20,100,20,20,601,10]),np.array([True,True,True,True,True,False]))
        np.testing.assert_array_equal(rows,[0,1])


if __name__=='__main__':unittest.main()
