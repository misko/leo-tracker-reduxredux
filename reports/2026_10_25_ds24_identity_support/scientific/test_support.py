"""Analytic support, normalization, stability and missed-mode controls."""
import unittest
import numpy as np
from scipy.special import logsumexp
from scipy.stats import norm,t
import support_geometry as g
import support_math as m
import support_bounds as b


class SupportTests(unittest.TestCase):
    def bank(self,knots,heights):
        positions=np.zeros((1,len(knots),3));positions[0,:,2]=heights
        return dict(time_s=np.asarray(knots,float),position_km=positions)

    def test_empty_and_full_support(self):
        for height in (-10.,10.):
            s=g.support(self.bank([-20,20],[height,height]),np.array([0.]),np.array([0,0,1.]),np.zeros(3),omega=0)
            self.assertTrue(s['certified']);self.assertEqual(s['root_brackets'],[])
            self.assertEqual(s['inner_visible_intervals'],[[-15.,15.]] if height>0 else [])

    def test_narrow_disconnected_visibility_is_not_grid_selected(self):
        bank=self.bank([-20,-.00003,0,.00003,1,1.00003,1.00006,20],[-1,-1,1,-1,-1,1,-1,-1])
        s=g.support(bank,np.array([0.]),np.array([0,0,1.]),np.zeros(3),omega=0)
        self.assertTrue(s['certified']);self.assertEqual(len(s['inner_visible_intervals']),2)
        self.assertGreater(sum(b-a for a,b in s['inner_visible_intervals']),5e-5)
        self.assertLess(sum(b-a for a,b in s['inner_visible_intervals']),7e-5)

    def test_piece_rotation_and_derivative(self):
        up=np.array([.6,0,.8]);observer=np.array([6.,0,4.]);position=np.array([7.,3.,5.]);slope=np.array([.1,-.2,.3])
        fun=g.piece_function(0.,position,slope,up,observer)
        for x in (-.7,.1,.9):
            h=1e-4;finite=(fun(x+h)[0]-fun(x-h)[0])/(2*h)
            self.assertAlmostEqual(float(finite),float(fun(x)[1]),places=9)

    def test_invalid_bank_and_extrapolation_fail(self):
        for knots,heights in (([0,0],[1,1]),([-20,20],[1,float('nan')]),([-2,2],[1,1])):
            with self.assertRaises(ValueError):g.support(self.bank(knots,heights),np.array([0.]),np.array([0,0,1.]),np.zeros(3))

    def test_tangent_is_not_silently_declared_positive(self):
        s=g.support(self.bank([-20,0,20],[-1,0,-1]),np.array([0.]),np.array([0,0,1.]),np.zeros(3),omega=0)
        self.assertEqual(s['inner_visible_intervals'],[])
        self.assertTrue(s['unresolved_intervals'] or s['root_brackets'])

    def test_prior_visible_mass_is_not_renormalized(self):
        distribution=t(3,loc=.2,scale=.7);normalization=distribution.cdf(15)-distribution.cdf(-15)
        fun=lambda x:np.full_like(x,-7.)+distribution.logpdf(x)-np.log(normalization)
        result=m.log_integrate(fun,np.array([[-1.,2.]]))
        expected=-7+np.log((distribution.cdf(2)-distribution.cdf(-1))/normalization)
        self.assertTrue(result['success']);self.assertAlmostEqual(result['log_integral'],expected,places=8)

    def test_positive_quadratic_dense_huge_residuals(self):
        rng=np.random.default_rng(27);n=7;u=rng.normal(size=(n,n));cov=u@u.T+np.eye(n)
        shape=rng.normal(size=(3,n,3))*1e3;raw=rng.normal(size=(3,n))*1e6;shifts=np.array([np.zeros(n),np.ones(n)*1e4])
        costs=m.positive_costs(raw,cov,shape,shifts)
        for phase in range(3):
            matrix=cov+shape[phase]@shape[phase].T;root=np.linalg.cholesky(matrix)
            for alias,shift in enumerate(shifts):
                z=np.linalg.solve(root,raw[phase]+shift)
                expected=z@z+2*np.log(np.diag(root)).sum()+n*np.log(2*np.pi)
                self.assertLess(abs(costs[phase,alias]-expected)/expected,1e-9)

    def test_extreme_log_density_and_independent_reference(self):
        fun=lambda x:-1e6+norm.logpdf(x,loc=.2,scale=.03)
        pieces=np.array([[-1.,.1],[.1,.2],[.2,.3],[.3,1.]])
        result=m.log_integrate(fun,pieces);ref=m.reference(fun,pieces)
        self.assertTrue(result['success']);self.assertTrue(ref['success'])
        self.assertLess(abs(result['log_integral']+1e6),1e-7)
        self.assertLess(abs(result['objective']-ref['objective']),1e-3)

    def test_narrow_off_grid_mode_correct_or_nonqualified(self):
        center=.1234567;width=1e-7
        fun=lambda x:-1000+norm.logpdf(x,loc=center,scale=width)
        pieces=np.array([[-1.,1.]])
        result=m.log_integrate(fun,pieces);ref=m.reference(fun,pieces)
        qualified=result['success'] and ref['success'] and abs(result['objective']-ref['objective'])<=1e-3
        if qualified:self.assertLess(abs(result['objective']-2000),1e-3)

    def test_separated_endpoint_modes(self):
        def fun(x):return logsumexp(np.stack((norm.logpdf(x,loc=-.999,scale=.0002),norm.logpdf(x,loc=.73,scale=.0004))),axis=0)-np.log(2)-1e6
        pieces=np.array([[-1.,-.998],[-.998,.729],[.729,.73],[.73,.731],[.731,1.]])
        result=m.log_integrate(fun,pieces);ref=m.reference(fun,pieces)
        if result['success'] and ref['success']:
            self.assertLess(abs(result['objective']-ref['objective']),1e-3)
        # Even if both rules miss the secondary peak, this analytic total must
        # reject a false convergence claim rather than accepting agreement.
        qualified=result['success'] and ref['success'] and abs(result['objective']-ref['objective'])<=1e-3
        if qualified:self.assertLess(abs(result['objective']-2e6),1e-3)

    def test_jointly_missed_99percent_mode_is_not_qualified(self):
        center=.123456789;sigma=1e-4
        def fun(x):return -1e6+np.logaddexp(np.log(.99)+norm.logpdf(x,loc=center,scale=sigma),np.log(.01/2))
        result=m.log_integrate(fun,[[-1.,1.]]);reference=m.reference(fun,[[-1.,1.]])
        self.assertTrue(result['success'] and reference['success'])
        self.assertGreater(abs(result['objective']-2e6),1)
        # A valid physical/analytic derivative envelope is mandatory, even
        # when both quadratures agree. The Gaussian-mixture derivative is at
        # most max|x-center|/sigma² on this domain.
        maximum=(1+abs(center))/sigma**2
        lower,upper=b.log_lipschitz_integrals(fun(np.array([0.])),np.array([maximum]),np.array([2.]))
        self.assertLessEqual(lower[0],-1e6);self.assertGreaterEqual(upper[0],-1e6)
        enclosure_qualified=2*(upper[0]-lower[0])<=1e-3
        self.assertFalse(enclosure_qualified)
        self.assertFalse(result['success'] and reference['success'] and enclosure_qualified)

    def test_physical_derivative_bounds_cover_mean_and_covariance_modes(self):
        from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
        from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
        knots=np.arange(-20.,21.)
        pos=np.stack((7000+knots*.1,knots*6,np.full(len(knots),200.)),axis=-1)[None]
        vel=np.broadcast_to(np.array([.1,6.,0.]),pos.shape).copy()
        dp=np.broadcast_to(np.eye(3)[:,None,:],(3,len(knots),3)).copy();dv=dp*.0001
        sky=dict(time_s=knots,position_km=pos,velocity_km_s=vel)
        mode=dict(time_s=knots,position_km=dp,velocity_km_s=dv)
        d=dict(target_sky=sky,target_mode_bank=mode,target_track={'times':np.array([0.,.2])})
        observer=np.array([6378.137,0.,0.]);center=np.array([.4]);half=np.array([.1]);q=np.array([.9,1.1])
        fd,bd=b.derivative_bounds(d,center,half,observer,q)
        for phi in np.linspace(.3,.5,11):
            h=1e-5;values=[];shapes=[]
            for phase in (phi-h,phi+h):
                values.append(paired_phase_frequency(sky,np.array([0.,.2]),np.zeros(2,int),np.array([phase]),0.,0.)[0]*q)
                shapes.append(paired_frequency_modes(sky,mode,np.array([0.,.2]),np.zeros(2,int),np.array([phase]),0.,0.)*q[:,None])
            self.assertTrue(np.all(abs((values[1]-values[0])/(2*h))<=fd[0]*(1+1e-7)))
            self.assertTrue(np.all(abs((shapes[1]-shapes[0])/(2*h))<=bd[0]*(1+1e-7)))

    def test_certified_order_is_separate_from_absolute_precision(self):
        from support_replay import certified_order
        null=dict(objective=100.,independent_dense_passed=True)
        rows=[dict(norad=1,status='complete',certified_visibility=True,
            full_support_lower_log_integral=-1000.,full_support_upper_log_integral=-900.,numerically_qualified=False)]
        proof=certified_order(rows,null)
        self.assertTrue(proof['proved']);self.assertEqual(proof['winner_kind'],'unresolved')
        self.assertFalse(proof['absolute_score_precision_implied'])
        rows[0]['full_support_upper_log_integral']=-40.
        self.assertFalse(certified_order(rows,null)['proved'])
        rows[0]['certified_visibility']=False
        self.assertFalse(certified_order(rows,null)['proved'])
        rows[0]=dict(norad=1,status='zero_physical_evidence',empty_support_certified=True,certified_visibility=True)
        self.assertTrue(certified_order(rows,null)['proved'])
        null['independent_dense_passed']=False
        self.assertFalse(certified_order(rows,null)['proved'])

    def test_physical_order_requires_strict_domination_and_includes_null(self):
        from support_replay import certified_order
        rows=[dict(norad=j,status='complete',certified_visibility=True,
            full_support_lower_log_integral=lo,full_support_upper_log_integral=hi) for j,lo,hi in ((1,-10,-9),(2,-12,-11))]
        null=dict(objective=40.,independent_dense_passed=True)
        self.assertEqual(certified_order(rows,null)['winner_norad'],1)
        rows[1]['full_support_upper_log_integral']=-10
        self.assertFalse(certified_order(rows,null)['proved'])
        for invalid in (float('nan'),float('inf'),-float('inf')):
            rows[1]['full_support_upper_log_integral']=invalid
            self.assertFalse(certified_order(rows,null)['proved'])
        rows[1]['full_support_upper_log_integral']=-13
        self.assertFalse(certified_order(rows,null)['proved'])


if __name__=='__main__':unittest.main()
