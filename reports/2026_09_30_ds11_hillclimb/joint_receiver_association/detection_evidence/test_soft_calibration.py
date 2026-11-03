import unittest
from soft_calibration import fit, windows


class SoftCalibrationTests(unittest.TestCase):
    def test_duplicates_do_not_change_fit(self):
        a = dict(window_id='w',label='same',delta_us=.01,cfo_hz=[1,2],exact=[.5,.6],control=[.1,.1])
        b = dict(a, label='different',delta_us=1.)
        self.assertEqual(fit([a,b],.03),fit([a]*30+[b]*20,.03))
        self.assertEqual(windows([a,b],.03),[('different',0.),('same',1.)])

    def test_unknown_and_extreme_labels_remain_soft(self):
        row=dict(window_id='w',label='unknown',delta_us=0,cfo_hz=[1,2],exact=[1,1],control=[0,0])
        self.assertEqual(fit([row],.03),{'same':.5,'different':.5})
        p=fit([dict(row,label='same')],.03)
        self.assertGreater(p['same'],.5)
        self.assertLess(p['same'],1.)
