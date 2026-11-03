import unittest
import numpy as np
from scipy.stats import norm,multivariate_normal
from scipy.special import roots_hermitenorm
from qualify import analytic_log_marginal,quadrature_log_marginal,interpolator_bounds


class TimingQuadratureTests(unittest.TestCase):
    def test_single_row_is_gaussian_convolution(self):
        for slope in [0.,20.,200.,2000.]:
            for r in [-200.,0.,3200.]:
                expected=norm.logpdf(r,scale=np.sqrt(125.**2+4*slope**2))
                self.assertAlmostEqual(analytic_log_marginal([r],[slope]),expected,places=12)

    def test_multivariate_oracle_and_determinant_lemma_with_heterogeneous_slopes(self):
        for m in [4,24]:
            slope=np.linspace(-200.,2000.,m);residual=.8*slope+np.linspace(-20.,20.,m)
            sigma=np.linspace(100.,150.,m);cov=np.diag(sigma**2)+4*np.outer(slope,slope)
            expected=multivariate_normal.logpdf(residual,cov=cov)
            got=analytic_log_marginal(residual,slope,sigma=sigma)
            self.assertAlmostEqual(got,expected,places=9)
            sign,logdet=np.linalg.slogdet(cov)
            self.assertEqual(sign,1.)
            self.assertAlmostEqual(logdet,2*np.log(sigma).sum()+np.log1p(4*np.sum((slope/sigma)**2)),places=10)

    def test_node_weight_scale_and_permutation_preserve_marginal(self):
        z,w=roots_hermitenorm(17);nodes=2*z;r=np.array([100.,120.,160.,200.]);g=np.array([20.,40.,50.,70.])
        expected=quadrature_log_marginal(r,g,nodes,w)
        order=np.arange(len(w))[::-1]
        self.assertAlmostEqual(quadrature_log_marginal(r,g,nodes[order],8*w[order]),expected,places=13)
        self.assertAlmostEqual(quadrature_log_marginal([0.],[0.],nodes,w),norm.logpdf(0,scale=125),places=13)

    def test_exact_segment_minimum_and_derivative_bound_cover_off_grid_site(self):
        p=np.array([[[7000.,-50.,0.],[7000.,50.,0.]]]);v=np.array([[[.1,7.,0.],[.2,7.1,0.]]]);nodes=[0.,1.]
        b=interpolator_bounds(p,v,nodes,rf_max_hz=12e9)
        self.assertTrue(b['valid']);self.assertAlmostEqual(b['minimum_range_km'][0],7000.-6378.137,places=10)
        for a in np.linspace(0,1,71):
            position=p[0,0]+a*(p[0,1]-p[0,0]);velocity=v[0,0]+a*(v[0,1]-v[0,0])
            site=np.array([6370.,0.,0.]);delta=position-site;r=np.linalg.norm(delta);u=delta/r
            pp=p[0,1]-p[0,0];vp=v[0,1]-v[0,0]
            up=(pp-u*(u@pp))/r
            exact=12e9/299792.458*abs(up@velocity+u@vp)
            self.assertLessEqual(exact,b['bound_hz_s'][0])
        invalid=interpolator_bounds(np.array([[[6000.,0.,0.],[6100.,0.,0.]]]),v,nodes,rf_max_hz=12e9)
        self.assertFalse(invalid['valid']);self.assertEqual(invalid['invalid_cells'],1)


if __name__=='__main__':unittest.main()
