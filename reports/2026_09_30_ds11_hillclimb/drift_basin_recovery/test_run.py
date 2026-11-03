import unittest
from run import deduplicate
class SeedTests(unittest.TestCase):
    def test_spatial_temporal_scan_and_qualification_rules(self):
        def a(x,index=0,qualified=True):return dict(job=dict(index=index),result=dict(endpoint=dict(x=x,qualified=qualified)))
        rows=[a([0,0,0]),a([.0001,0,0]),a([.002,0,0]),a([0,0,.002]),a([0,0,0],1),a([4,4,4],qualified=False)]
        self.assertEqual([j['parent_job'] for j in deduplicate(rows)],[0,2,3,4])
    def test_no_geographic_seed_selection(self):
        rows=[dict(job=dict(index=0),result=dict(endpoint=dict(x=[0,0,0],qualified=True,error_m=1)))]
        before=deduplicate(rows);rows[0]['result']['endpoint']['error_m']=1e9
        self.assertEqual(before,deduplicate(rows))
if __name__=='__main__':unittest.main()
