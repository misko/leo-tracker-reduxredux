"""Explicit RF hypotheses over the same recorded IF observations."""
from dataclasses import replace
import numpy as np


MODES=('recorded','static-9750','static-10600')


def remap(observations,targets,mode):
    if mode not in MODES:raise ValueError('Unknown declared RF mapping hypothesis')
    reference={}
    for target in targets:
        channel=int(target['channel'])
        row=(float(target['rf_center_hz']),float(target['lnb_lo_hz']),float(target['if_center_hz']))
        if channel in reference and reference[channel]!=row:raise ValueError('Ambiguous channel tuning target')
        if abs(row[0]-row[1]-row[2])>.01:raise ValueError('Recorded RF/LO/IF arithmetic does not close')
        reference[channel]=row
    rf=np.empty(len(observations.times_s))
    for channel in np.unique(observations.channel):
        if int(channel) not in reference:raise ValueError('Observation channel lacks a recorded tuning target')
        nominal,lo,_=reference[int(channel)];selected=observations.channel==channel
        if np.any(abs(observations.rf_hz[selected]-nominal)>.01):
            raise ValueError('Observation RF does not match the recorded target hypothesis')
        alternative=lo if mode=='recorded' else (9.75e9 if mode=='static-9750' else 10.6e9)
        rf[selected]=observations.rf_hz[selected]-lo+alternative
    return replace(observations,rf_hz=rf)


def calibration_seed(frozen_model,fit,joint):
    """Carry the same physical frequency correction into the new RF hypothesis.

    Orbital predictions intentionally change with RF. This transport preserves
    receiver correction only and does not claim objective equality across maps.
    """
    if joint.observations.window_ids!=frozen_model.observations.window_ids:
        raise ValueError('RF hypotheses must retain the original observation inventory')
    v=np.array(fit['vector'],float,copy=True);n=np.array(fit['nuisance'],float,copy=True)
    correction=frozen_model.original.correction(v,n[:frozen_model.base_nuisance_count])
    if frozen_model.original.group_count or joint.group_count!=joint.offset_count:
        raise ValueError('Offset-only target and frozen-band source required')
    if joint.clock_count!=frozen_model.clock_count:
        raise ValueError('Common clock layout changed across RF hypotheses')
    clock=n[:joint.clock_count].copy()
    # Keep c and the common-clock function exactly fixed. Only receiver
    # intercept/contrast need rebasing when RF differences are band constants.
    nonconstant=(joint.design[:,1]*v[3]+joint.design[:,3]*v[5]+
                 joint.design[:,4]*v[6]+joint.base.clock_design@clock+joint.baseline)
    remaining=correction-nonconstant;offsets=[]
    obs=joint.observations
    for rx,fraction in zip(joint.frame.receivers,joint.frame.high_fractions,strict=True):
        low=(obs.receiver==rx)&(obs.channel<=4);high=(obs.receiver==rx)&(obs.channel>=5)
        if not low.any() or not high.any():raise ValueError('Both channel groups required for receiver rebase')
        a=float(remaining[low].mean());b=float(remaining[high].mean());offsets.append(b-a)
        v[2+2*rx]=a+fraction*(b-a)
    nn=np.r_[clock,offsets,n[frozen_model.base_nuisance_count:]]
    actual=joint.correction(v,nn[:len(joint.initial_nuisance)])
    error=float(np.max(abs(actual-correction)))
    if error>=1e-6:raise ValueError('New RF hypothesis cannot carry the original receiver correction exactly')
    return v,nn,dict(maximum_correction_error_hz=error,
                    projection_rms_hz=float(np.sqrt(np.mean((actual-correction)**2))))
