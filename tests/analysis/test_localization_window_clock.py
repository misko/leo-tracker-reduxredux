import numpy as np
from leo.analysis.localization_windows import independent_scan_columns,independent_scan_precision
from leo.analysis.localization_window_clock import common_clock_layout
from leo.analysis.localization_windows import WindowTrackPort
from leo.analysis.gaussian_sum_location import Prediction
from leo.analysis.localization_fast import fit_localization_fast


def test_one_scan_is_identical():
    columns,precision=common_clock_layout([7])
    np.testing.assert_array_equal(columns[0],independent_scan_columns([7])[0])
    np.testing.assert_array_equal(precision,independent_scan_precision([7]))


def test_clock_shared_but_other_nuisances_disjoint():
    columns,precision=common_clock_layout([2,3,4,5])
    assert len(precision)==3+sum(2+n for n in [2,3,4,5])
    assert all(c[2]==2 for c in columns)
    for i,c in enumerate(columns):
        assert len(c)==5+[2,3,4,5][i]
        for d in columns[i+1:]:assert set(c[3:]).isdisjoint(d[3:])
    state=np.zeros(len(precision));state[2]=2
    assert .5*(precision*state)@state==2. # One prior, not four copies.


def test_common_clock_joint_solver_matches_closed_form():
    class Port:
        candidate_count=1
        priors_piecewise_constant=True

        def __init__(self,name,clock,scale):
            self.observation_ids=tuple(name+str(i) for i in range(4))
            self.matrix=np.zeros((4,6))
            self.matrix[:,:3]=[[1,0,scale],[0,1,1],[1,1,-1],[2,-1,scale]]
            self.observation=self.matrix@np.array([2.,-3.,clock,0,0,0])

        def predict_selected(self,state,index):
            return Prediction(self.matrix@state,self.matrix,np.eye(4),True)

        def score_selected(self,state,index):
            if index==1:return -1e6
            r=self.observation-self.matrix@state
            return float(-.5*r@r)

        def score_all(self,state):
            return np.array([self.score_selected(state,0),-1e6])

    columns,precision=common_clock_layout([1,1])
    locals=[Port('first',3.,1.),Port('second',-2.,2.)]
    ports=[WindowTrackPort(p,c,len(precision)) for p,c in zip(locals,columns)]
    zero=np.zeros(len(precision))
    design=np.vstack([p.predict_selected(zero,0).jacobian for p in ports])
    observations=np.concatenate([p.observation for p in ports])
    expected=np.linalg.solve(design.T@design+np.diag(precision),design.T@observations)
    fit=fit_localization_fast(zero,ports,precision,lambda x:np.linalg.norm(x[:2])<250,max_iterations=32)
    assert fit.converged
    np.testing.assert_allclose(fit.mean,expected,atol=1e-8)
