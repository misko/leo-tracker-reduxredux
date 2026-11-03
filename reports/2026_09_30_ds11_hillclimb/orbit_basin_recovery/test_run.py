import unittest
from run import recovery,read,HILL

class SeedTests(unittest.TestCase):
    def test_actual_qualified_coverage_and_no_reference_dependence(self):
        attempts=read(HILL/'joint_orbit_position/selections.json')['attempts']
        jobs=recovery.deduplicate(attempts)
        self.assertEqual({j['index'] for j in jobs},{0,16})
        for a in attempts:
            if a['result'] and a['result']['endpoint']['qualified']:
                x=a['result']['endpoint']['x']
                self.assertTrue(any(j['index']==a['job']['index'] and
                    sum((j['seed'][k]-x[k])**2 for k in (0,1))<=.001**2 and abs(j['seed'][2]-x[2])<=.001 for j in jobs))
                a['result']['endpoint']['estimate_deg']=[90,0]
        self.assertEqual(jobs,recovery.deduplicate(attempts))

    def test_failed_endpoints_cannot_seed(self):
        self.assertEqual(recovery.deduplicate([dict(job=dict(index=0),result=None),
            dict(job=dict(index=0),result=dict(endpoint=dict(qualified=False,x=[0,0,0])))]),[])
