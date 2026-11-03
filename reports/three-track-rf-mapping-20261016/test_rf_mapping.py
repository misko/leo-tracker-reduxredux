import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'three-track-joint-band-recalibration-20261016'))
from test_band_transport import fixture
from rf_mapping import remap,calibration_seed
from leo.application.channel_group_refinement import objective
from types import SimpleNamespace
from leo.analysis.hard60_score import predict_orbits


def targets(obs):
    result=[]
    for channel in np.unique(obs.channel):
        rf=float(obs.rf_hz[obs.channel==channel][0]);lo=9.75e9 if channel<=4 else 10.6e9
        result.append(dict(channel=int(channel),rf_center_hz=rf,lnb_lo_hz=lo,if_center_hz=rf-lo))
    return result


class MappingTests(unittest.TestCase):
    def test_recorded_and_static_lo_arithmetic_preserve_cfo_time_inventory(self):
        old,fit,shift,joint=fixture();obs=old.observations;reference=targets(obs)
        recorded=remap(obs,reference,'recorded');np.testing.assert_array_equal(recorded.rf_hz,obs.rf_hz)
        low=remap(obs,reference,'static-9750');high=remap(obs,reference,'static-10600')
        np.testing.assert_array_equal(low.rf_hz,obs.rf_hz-(obs.channel>=5)*850e6)
        np.testing.assert_array_equal(high.rf_hz,obs.rf_hz+(obs.channel<=4)*850e6)
        for mapped in [recorded,low,high]:
            self.assertEqual(mapped.window_ids,obs.window_ids)
            for name in ['times_s','measured_hz','channel','receiver','margin']:
                np.testing.assert_array_equal(getattr(mapped,name),getattr(obs,name))

    def test_receiver_calibration_transports_exactly_in_each_rf_arm(self):
        for c in [-250.,0.]:
            old,fit,shift,joint=fixture(c)
            for mode in ['recorded','static-9750','static-10600']:
                mapped=remap(old.observations,targets(old.observations),mode)
                new=objective(SimpleNamespace(observations=mapped),old.bank,old.prior,np.arange(0,301,30.))
                v,n,receipt=calibration_seed(old,fit,new)
                self.assertLess(receipt['maximum_correction_error_hz'],1e-6)
                self.assertEqual(v[6],c)
                np.testing.assert_allclose(v[7:],fit['vector'][7:],rtol=0,atol=0)
                np.testing.assert_allclose(n[len(new.initial_nuisance):],fit['nuisance'][old.base_nuisance_count:],rtol=0,atol=0)

    def test_unknown_or_inconsistent_mapping_is_rejected(self):
        old,*_=fixture();obs=old.observations;reference=targets(obs)
        with self.assertRaises(ValueError):remap(obs,reference,'arbitrary')
        reference[0]['if_center_hz']+=100
        with self.assertRaises(ValueError):remap(obs,reference,'static-9750')
        with self.assertRaises(ValueError):remap(obs,[],'recorded')

    def test_hypothesis_changes_doppler_by_the_declared_rf_ratio(self):
        old,fit,*_=fixture();obs=old.observations;v=fit['vector']
        timings=v[7]+old.basis@v[8:]
        before=predict_orbits(old.bank,obs,old.prior,v[:2],timings,derivatives=False)[0]
        for mode in ['static-9750','static-10600']:
            mapped=remap(obs,targets(obs),mode)
            after=predict_orbits(old.bank,mapped,old.prior,v[:2],timings,derivatives=False)[0]
            np.testing.assert_allclose(after,before*(mapped.rf_hz/obs.rf_hz)[:,None],rtol=1e-14,atol=1e-8)


if __name__=='__main__':unittest.main()
