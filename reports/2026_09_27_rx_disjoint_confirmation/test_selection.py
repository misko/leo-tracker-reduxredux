import unittest
from select_cohort import select


class Tests(unittest.TestCase):
    def rows(self):return [{'session_id':str(i),'tracking_status_observed_at_inventory':'complete','source_span_attested':True} for i in range(20)]
    def test_order_independent(self):
        self.assertEqual(select(self.rows(),{'1'}),select(self.rows()[::-1],{'1'}))
    def test_exclusion(self):
        selected,_=select(self.rows(),{'1','2','3'})
        self.assertFalse({r['session_id'] for r in selected}&{'1','2','3'})
    def test_outcomes_ignored(self):
        a=self.rows();b=self.rows()
        for r in b:r['location_error_km']=999
        self.assertEqual([r['session_id'] for r in select(a,set())[0]],[r['session_id'] for r in select(b,set())[0]])
    def test_insufficient(self):
        with self.assertRaises(ValueError):select(self.rows(),{str(i) for i in range(20)})


if __name__=='__main__':unittest.main()
