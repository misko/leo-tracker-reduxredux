"""Independent numerical controls for the grouped prediction witness."""
import unittest
import numpy as np
from types import SimpleNamespace
from adapter import expand
from witness import nuisance_projector,project,statistics,predictive,fast_basis

class WitnessTests(unittest.TestCase):
    def test_predictive_matches_dense_joint_normal(self):
        rng=np.random.default_rng(317)
        u=rng.normal(size=(25,4));v=rng.normal(size=(13,4));y=rng.normal(size=25);z=rng.normal(size=13);sigma=1.7
        got=predictive(statistics(y,u,len(y)),statistics(z,v,len(z)),sigma)
        a=np.eye(4)+u.T@u/sigma**2;cov=np.linalg.inv(a);mu=cov@u.T@y/sigma**2
        target=np.eye(len(z))*sigma**2+v@cov@v.T;r=z-v@mu
        expected=len(z)*np.log(2*np.pi)+np.linalg.slogdet(target)[1]+r@np.linalg.solve(target,r)
        self.assertAlmostEqual(got['negative_twice_log_density'],expected,places=11)

    def test_design_projection_removes_nuisance_without_learning_target(self):
        t=np.linspace(-1,1,31);design=np.column_stack((np.ones(31),t,t*t))
        q,rank=nuisance_projector(design);self.assertEqual(rank,3)
        y=np.sin(9*t);changed=y+design@np.array([700.,-900.,1100.])
        np.testing.assert_allclose(project(y,q),project(changed,q),atol=1e-10)

    def test_correlated_target_vector_is_not_independent_votes(self):
        train=statistics(np.zeros(8),np.ones((8,1)),8)
        test=statistics(np.ones(12)*3,np.ones((12,1)),12)
        joint=predictive(train,test,1.)['negative_twice_log_density']
        separate=sum(predictive(train,statistics(np.array([3.]),np.ones((1,1)),1),1.)['negative_twice_log_density'] for _ in range(12))
        self.assertGreater(separate-joint,20.)

    def test_shared_signal_predicts_independent_families(self):
        rng=np.random.default_rng(44);time=np.linspace(0,300,251);rx=np.ones(len(time));q=np.ones(len(time))
        b=fast_basis(time,rx,q,'fast_rx1_rf50');beta=rng.normal(size=b.shape[1]);sigma=15.
        train=b@beta+rng.normal(0,sigma,len(time));test=b@beta+rng.normal(0,sigma,len(time))
        proper=predictive(statistics(train,b,len(time)),statistics(test,b,len(time)),sigma)
        shifted=fast_basis(time,rx,q,'fast_rx1_rf50',training_control='shift75')
        control=predictive(statistics(train,shifted,len(time)),statistics(test,b,len(time)),sigma)
        self.assertGreater(control['negative_twice_log_density']-proper['negative_twice_log_density'],100.)

    def test_wrong_receiver_training_cannot_learn_rx1_signal(self):
        t=np.linspace(0,300,301);rx=np.ones(len(t));q=np.ones(len(t))
        native=fast_basis(t,rx,q,'fast_rx1_rf50');wrong=fast_basis(t,rx,q,'fast_rx1_rf50',training_control='wrong_RX')
        self.assertGreater(np.linalg.norm(native),0.);self.assertEqual(np.linalg.norm(wrong),0.)

    def test_independent_family_noise_does_not_gain_on_average(self):
        rng=np.random.default_rng(617);t=np.linspace(0,300,121);b=fast_basis(t,np.ones(len(t)),np.ones(len(t)),'fast_rx1_rf50')/50
        total=0.
        for _ in range(30):
            y=rng.normal(size=len(t));z=rng.normal(size=len(t))
            baseline=predictive(statistics(y,np.zeros((len(t),0)),len(t)),statistics(z,np.zeros((len(t),0)),len(t)),1.)
            candidate=predictive(statistics(y,b,len(t)),statistics(z,b,len(t)),1.)
            total+=baseline['negative_twice_log_density']-candidate['negative_twice_log_density']
        self.assertLess(total,0.)

    def test_position_adapter_clones_inputs_and_preserves_Hz_loading(self):
        t=np.linspace(0,300,21)
        tracks=[dict(times=t,receiver=1,rf_hz=12.5e9),dict(times=t,receiver=2,rf_hz=10.5e9)]
        scan=SimpleNamespace(tracks=tracks,rx_basis=[np.ones((len(t),11)),np.ones((len(t),11))])
        original=dict(scan=scan,node={'seed':{'state':{'smooth':np.ones((2,11))}}})
        changed=expand(original,'fast_rx1_hz50')
        self.assertIsNot(changed['scan'],scan)
        self.assertEqual(scan.rx_basis[0].shape,(len(t),11))
        self.assertEqual(np.asarray(original['node']['seed']['state']['smooth']).shape,(2,11))
        from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
        expected=projected_receiver_basis(t,spacing_s=10.,width_s=5.)*50.
        np.testing.assert_allclose(changed['scan'].rx_basis[0][:,11:]*200*12.5/11.5,expected,atol=1e-12)
        self.assertEqual(np.linalg.norm(changed['scan'].rx_basis[1][:,11:]),0.)

if __name__=='__main__':unittest.main()
