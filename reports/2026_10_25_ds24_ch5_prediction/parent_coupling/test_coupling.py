import unittest
import numpy as np
import coupling_math as cm


class CouplingTests(unittest.TestCase):
    def fixture(self):
        rng=np.random.default_rng(2026102521)
        n,p=28,8;selected=np.arange(n)<13
        h=rng.normal(size=(n,p));h[~selected,:4]=0
        precision=np.array([1/9.,.7,1.2,3.,1.,1.,.2,2.])
        mean=np.zeros(p);mean[0]=1.2
        intercept=rng.normal(size=n);variance=np.linspace(.5,1.5,n)
        values=intercept+h@mean+rng.normal(size=n)
        d=cm.reduce_family(values,intercept,h,precision,variance,mean,selected,
                           0,[1,2,3],2.,2.4)
        d['covariance_root']=np.linalg.cholesky(d['covariance'])
        return d

    def test_original_full_Gaussian_closure_and_removed_columns(self):
        d=self.fixture()
        self.assertLess(abs(d['Gaussian_closure_error']),1e-10)
        np.testing.assert_array_equal(d['removed_columns'],[0,1,2,3])
        self.assertAlmostEqual(d['prior_sd'],6.)

    def test_rank3_matches_independent_dense(self):
        d=self.fixture();phi=np.array([-2.,.3,4.])
        frequency=d['affine_intercept']+phi[:,None]*d['derivative']
        b=np.broadcast_to(d['frozen_modes'],(len(phi),*d['frozen_modes'].shape)).copy()
        b*=np.array([.7,1.,1.3])[:,None,None]
        costs=cm.node_costs(d['raw'],d['covariance'],frequency,b)
        dense=[cm.dense_node_cost(d['raw'],d['covariance'],f,bb) for f,bb in zip(frequency,b)]
        np.testing.assert_allclose(costs,dense,atol=1e-10,rtol=1e-12)

    def test_affine_frozen_B_exact_truncated_density(self):
        d=self.fixture()
        def evaluate(phi):
            return (d['affine_intercept']+np.asarray(phi)[:,None]*d['derivative'],
                np.broadcast_to(d['frozen_modes'],(len(phi),*d['frozen_modes'].shape)),
                np.full((len(phi),len(d['raw'])),45.))
        expected=(d['affine_conditional_objective']-
            2*np.log(cm.domain_mass(d['proposal_mean'],d['proposal_sd'])[0])+
            2*np.log(cm.domain_mass(d['prior_mean'],d['prior_sd'])[0]))
        for branch in ('frozen','dynamic'):
            for n in (21,41):
                result=cm.integrate(d,evaluate,branch,n)
                self.assertAlmostEqual(result['objective'],expected,places=9)
            reference=cm.adaptive_reference(d,evaluate,branch)
            self.assertAlmostEqual(reference['objective'],expected,places=7)

    def test_narrow_phase_rule_uses_posterior_not_uniform_phase_grid(self):
        d=dict(raw=np.array([800.]),covariance=np.eye(1),frozen_modes=np.zeros((1,3)),
            prior_mean=0.,prior_sd=5.,proposal_mean=800000/(1000000+1/25),
            proposal_sd=np.sqrt(1/(1000000+1/25)))
        d['covariance_root']=np.eye(1)
        def evaluate(phi):
            return np.asarray(phi)[:,None]*1000,np.zeros((len(phi),1,3)),np.ones((len(phi),1))*45
        result=cm.integrate(d,evaluate,'dynamic',41)
        reference=cm.adaptive_reference(d,evaluate,'dynamic')
        self.assertLess(abs(result['objective']-reference['objective']),1e-7)
        self.assertLess(result['sampled_phase_range_s'][1]-result['sampled_phase_range_s'][0],.01)


if __name__=='__main__':unittest.main()
