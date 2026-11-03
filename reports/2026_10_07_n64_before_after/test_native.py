import time
import unittest
import numpy as np
import data
from native_score import NativeObjective,predict_orbits
from leo.analysis.regional_position_score import PositionObjective,predict_orbits as oracle
import leo.analysis.regional_position_bootstrap as bootstrap

class NativeChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.d,cls.obs,cls.bank,cls.prior,cls.score=data.load('N01')
    def test_orbit_values_derivatives_and_visibility(self):
        small=self.bank.select([0,100,400,800])
        for point in ([0,0],[-100,-80],[200,100]):
            shifts=np.array([-20.,-1.234,2.34,20.])
            old=oracle(small,self.obs,self.prior,point,shifts)
            new=predict_orbits(small,self.obs,self.prior,point,shifts)
            for a,b in zip(old,new):np.testing.assert_allclose(a,b,rtol=1e-12,atol=1e-9)
        with self.assertRaises(ValueError):predict_orbits(small,self.obs,self.prior,[0,0],np.full(4,10000.))
    def test_objective_and_bootstrap(self):
        start=time.monotonic()
        original=bootstrap.predict_orbits
        try:
            bootstrap.predict_orbits=oracle
            old=bootstrap.bootstrap_position(self.obs,self.bank,self.prior,[-50,-50],self.d['bootstrap_tracks'],maximum_seconds=30)
            old_seconds=time.monotonic()-start
            bootstrap.predict_orbits=predict_orbits
            start=time.monotonic()
            new=bootstrap.bootstrap_position(self.obs,self.bank,self.prior,[-50,-50],self.d['bootstrap_tracks'],maximum_seconds=30)
            new_seconds=time.monotonic()-start
        finally:bootstrap.predict_orbits=original
        self.assertEqual(old.satellite_indices,new.satellite_indices)
        np.testing.assert_allclose(old.vector,new.vector,atol=1e-7,rtol=1e-9)
        for a,b in zip(old.matches,new.matches):
            self.assertEqual((a.rows,a.satellite_index,a.timing_s),(b.rows,b.satellite_index,b.timing_s))
            np.testing.assert_allclose([a.shape_rms_hz,a.shape_cost],[b.shape_rms_hz,b.shape_cost],atol=1e-7,rtol=1e-10)
        selected=self.bank.select(list(old.satellite_indices))
        a=PositionObjective(self.obs,selected,self.prior,self.score)
        b=NativeObjective(self.obs,selected,self.prior,self.score)
        for perturb in (0.,.1):
            v=old.vector.copy()+perturb
            oa,ga,ta=a.evaluate(v);ob,gb,tb=b.evaluate(v)
            np.testing.assert_allclose(oa,ob,atol=1e-7,rtol=0)
            np.testing.assert_allclose(ga,gb,atol=1e-7,rtol=1e-8)
            for field in ('responsibilities','clutter_probability','residual_hz','prediction_gradient'):
                np.testing.assert_allclose(getattr(ta,field),getattr(tb,field),atol=1e-8,rtol=1e-8)
        start=time.monotonic()
        for _ in range(20):b.evaluate(old.vector)
        print('BENCHMARK bootstrap original/native',old_seconds,new_seconds,'native evaluate',(time.monotonic()-start)/20,flush=True)

if __name__=='__main__':unittest.main(verbosity=2)
