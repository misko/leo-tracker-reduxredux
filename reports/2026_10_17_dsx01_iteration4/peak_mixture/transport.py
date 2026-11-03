"""Exact empirical-center rebase; clock coefficients, q and timing unchanged."""
import numpy as np
from leo.analysis.sequential_group_calibration import freeze_sequential_calibration


def rebase_vector(vector,old_observations,new_observations):
    v=np.asarray(vector,float).copy()
    dt=new_observations.time_center_s-old_observations.time_center_s
    df=(new_observations.rf_center_hz-old_observations.rf_center_hz)/1e9
    v[2]+=v[3]*dt+v[6]*df
    v[4]+=v[5]*dt+v[6]*df
    return v


def transport(old,new,vector,nuisance,shift):
    """Prove closure against the public complete frozen correction function."""
    np.testing.assert_array_equal(old.original.base.nodes,new.original.base.nodes)
    if old.base_nuisance_count!=new.base_nuisance_count:
        raise ValueError('Unchanged clock/nuisance dimension required')
    v=rebase_vector(vector,old.observations,new.observations)
    n=np.asarray(nuisance,float).copy()
    complete=freeze_sequential_calibration(old.original,
        dict(vector=vector,nuisance=n[:old.base_nuisance_count]),shift)
    obs=new.observations
    expected=complete.predict(obs.times_s,obs.rf_hz,obs.receiver,obs.channel>=5)
    actual=new.original.correction(v,n[:new.base_nuisance_count])
    error=float(np.max(abs(expected-actual),initial=0))
    if error>1e-6:raise ValueError('Complete calibration transport failed closure')
    return v,n,dict(maximum_correction_error_hz=error,
        old_time_center_s=float(old.observations.time_center_s),
        new_time_center_s=float(obs.time_center_s),
        old_rf_center_hz=float(old.observations.rf_center_hz),
        new_rf_center_hz=float(obs.rf_center_hz),
        unchanged_clock_q_and_timing=True)
