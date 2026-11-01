import copy
import unittest
from policy import select, ARMS


class PolicyTests(unittest.TestCase):
    def fixture(self):
        baseline={a:dict(error_m=1000,x=[1,2],objective=100,rms_hz=80,associated=40) for a in ARMS}
        fit=dict(qualified=True,all_gates_pass=True,phase_closed=True,optimizer_success=True,
                 mixture_phase_interior=True,native_ids_sha256='same',lost_ids=[],unexpected_reassigned_ids=[],
                 error_m=2000,x=[2,3],objective=90,rms_hz=75)
        record=dict(name='old_to_new',accepted=True,gains=dict(c0=10.,fitted_c=10.),
                    pair={a:copy.deepcopy(fit) for a in ARMS},control={a:dict(native_ids_sha256='same') for a in ARMS})
        guard=dict(passed=True,model='receiver_offset',unique_folds=5,missing=[],minimum_margin=1.)
        return baseline,record,guard

    def test_error_cannot_select_or_veto(self):
        b,r,g=self.fixture()
        self.assertEqual(select(b,[r],{r['name']:g})['selected'],r['name'])
        r['pair']['c0']['error_m']=1e9;r['pair']['fitted_c']['error_m']=1e9
        self.assertEqual(select(b,[r],{r['name']:g})['selected'],r['name'])

    def test_exact_fallback_missing_guard_or_failed_arm(self):
        b,r,g=self.fixture()
        self.assertEqual(select(b,[r],{})['final'],b)
        r['pair']['c0']['phase_closed']=False
        self.assertEqual(select(b,[r],{r['name']:g})['final'],b)

    def test_no_prior_only_or_continuation(self):
        b,r,g=self.fixture()
        self.assertEqual(select(b,[],{})['final'],b)

    def test_guard_not_interchangeable_or_duplicate(self):
        for key,value in [('model','track_offset'),('unique_folds',4),('minimum_margin',0.),('minimum_margin',float('nan'))]:
            b,r,g=self.fixture();g[key]=value
            self.assertIsNone(select(b,[r],{r['name']:g})['selected'])

    def test_native_evidence_and_ownership(self):
        b,r,g=self.fixture();r['pair']['fitted_c']['native_ids_sha256']='changed'
        self.assertIsNone(select(b,[r],{r['name']:g})['selected'])
        b,r,g=self.fixture();r['pair']['c0']['lost_ids']=['x']
        self.assertIsNone(select(b,[r],{r['name']:g})['selected'])


if __name__=='__main__':unittest.main()
