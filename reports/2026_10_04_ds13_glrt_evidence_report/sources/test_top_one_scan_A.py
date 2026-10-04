import unittest
from top_one_scan_A import winners

def row(i,rx,margin,status='refined'):
    return dict(row_index=i,probe_key=[42,rx,0],original_margin=margin,refinement=dict(status=status,**({'margin':margin} if status=='refined' else {})))

class Tests(unittest.TestCase):
    def test_receiver_independence_and_maximum(self):
        self.assertEqual(winners([row(1,0,.3),row(2,0,.7),row(3,1,.4)]),{2,3})
    def test_ties_and_no_point_six_gate(self):
        self.assertEqual(winners([row(2,0,.1),row(1,0,.1)]),{1})
    def test_failed_refinement_fallback(self):
        self.assertEqual(winners([row(1,0,.4,'no_local_maximum'),row(2,0,.3)]),{1})

if __name__=='__main__':unittest.main()
