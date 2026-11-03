"""Independent synthetic receiver-clock initializer invariants, no orbit model."""
import unittest
import numpy as np
from leo.contracts.regional_position import PositionObservations
from leo.analysis.regional_position_score import ALIAS_HZ
from experiment import clock_seed,clock_metrics

class ClockInitializerTests(unittest.TestCase):
    def synthetic(self):
        count=40;t=np.linspace(-20,20,count)
        times=np.column_stack([t-2.5e-8,t+2.5e-8]).reshape(-1)
        rx=np.tile([0,1],count);rf=np.repeat(1e9+np.arange(count)%3*2.5e8,2)
        channel=np.repeat(np.arange(count)%3+1,2)
        obs=PositionObservations(tuple(f'w{i}' for i in range(2*count)),times,np.zeros(2*count),rf,rx,channel,np.ones(2*count))
        centered=times-obs.time_center_s
        design=np.column_stack([rx==0,(rx==0)*centered,rx==1,(rx==1)*centered,(rf-obs.rf_center_hz)/1e9])
        baseline=10*np.sin(times/3)+rx*(50+times*.1)
        class NoOrbit:
            def __getattr__(self,name):raise AssertionError(f'initializer accessed unexpected model field {name}')
        base=NoOrbit();base.baseline=baseline;base.design=design
        v=np.r_[[-93.75,-81.25],[-135.,-10.,165.,16.,-765.],[-3.,.5,2.,-1.]]
        true=v.copy();true[2],true[4]=15-173/2,15+173/2;true[3],true[5]=3-.75/2,3+.75/2
        common=np.repeat(400*np.sin(t/4)+37*t,2)
        y=common+design@true[2:7]+baseline
        # Independent alias integers must not corrupt a paired physical difference.
        y[1::2]+=2*ALIAS_HZ;y[::2]-=ALIAS_HZ
        obs=PositionObservations(obs.window_ids,times,y,rf,rx,channel,np.ones(2*count))
        pairs=np.arange(2*count).reshape(-1,2)
        return obs,base,v,true,pairs

    def test_recovers_differential_terms_and_preserves_physical_state(self):
        obs,base,v,true,pairs=self.synthetic();original=v.copy()
        result,meta=clock_seed(obs,base,v,pairs)
        np.testing.assert_array_equal(v,original)
        np.testing.assert_array_equal(result[:2],v[:2])
        np.testing.assert_array_equal(result[6:],v[6:])
        self.assertAlmostEqual((result[2]+result[4])/2,(v[2]+v[4])/2,places=12)
        self.assertAlmostEqual((result[3]+result[5])/2,(v[3]+v[5])/2,places=12)
        np.testing.assert_allclose(result[2:6],true[2:6],atol=1e-9,rtol=0)
        self.assertAlmostEqual(meta['differential_offset_hz'],173,places=9)
        self.assertAlmostEqual(meta['differential_slope_hz_s'],.75,places=9)
        i,j=pairs.T
        np.testing.assert_array_equal(obs.rf_hz[i],obs.rf_hz[j])
        np.testing.assert_array_equal(base.design[i,4],base.design[j,4])

    def test_clock_metrics_detect_and_remove_spurious_differential_drift(self):
        obs,base,v,true,pairs=self.synthetic()
        before=clock_metrics(obs,base,v,pairs);result,_=clock_seed(obs,base,v,pairs)
        after=clock_metrics(obs,base,result,pairs)
        self.assertGreater(before['median_absolute_residual_hz'],100)
        self.assertGreater(abs(before['robust_residual_slope_hz_s']),20)
        self.assertLess(after['median_absolute_residual_hz'],1e-8)
        self.assertLess(after['p90_absolute_residual_hz'],1e-8)
        self.assertLess(abs(after['robust_residual_slope_hz_s']),1e-9)

if __name__=='__main__':unittest.main()
