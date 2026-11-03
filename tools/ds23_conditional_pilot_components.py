"""Held-symbol prediction of two received pilot components in one RF probe.

Each intersection of their frame supports has complex gains per tone and DC.
Timing/CFO/rate are conditioned on earlier RF fits. Rolled-symbol controls have
the same channel dimension. No orbital or geographic information is used.
"""

import numpy as np
from frequency_selective_pilot import ChannelPilotWorkspace
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S


def component_geometry(samples,fs,edge,epoch,fit):
    p=ChannelPilotWorkspace(samples,fs,edge,epoch)
    offset,ppm=fit['offset_samples'],fit['modulation_ppm']
    local=(p.n-epoch-offset)*(1+ppm*1e-6)/fs
    frame=np.floor(local*750).astype(int);phase=local-frame/750
    valid=(frame>=0)&(frame<len(p.frames))&(phase>=16/fs)&(phase<1/750-16/fs)
    rotation=np.exp(2j*np.pi*fit['CFO_hz']*(p.t-p.mid))[:,None]
    exact=p.columns(offset,ppm)*rotation;control=p.columns(offset,ppm,True)*rotation
    symbol=np.floor(phase/OFDM_SYMBOL_DURATION_S).astype(int)
    return dict(exact=exact,control=control,frame=frame,valid=valid,symbol=symbol)


def component_segments(first,second):
    valid=first['valid']&second['valid']
    labels=np.where(valid,first['frame']*10000+second['frame'],-1)
    boundaries=np.r_[0,np.flatnonzero(np.diff(labels)!=0)+1,len(labels)]
    return [np.arange(a,b) for a,b in zip(boundaries[:-1],boundaries[1:],strict=True) if labels[a]>=0 and b-a>=80]


def conditional_component_prediction(samples,fs,edge,first_epoch,first_fit,second_epoch,second_fit):
    y=np.asarray(samples,complex)
    first=component_geometry(y,fs,edge,first_epoch,first_fit)
    second=component_geometry(y,fs,edge,second_epoch,second_fit)
    constant=np.ones((len(y),1))
    designs=dict(first=np.column_stack((first['exact'],constant)),
        second=np.column_stack((second['exact'],constant)),
        joint=np.column_stack((first['exact'],second['exact'],constant)),
        second_control=np.column_stack((first['exact'],second['control'],constant)),
        first_control=np.column_stack((first['control'],second['exact'],constant)))
    segments=component_segments(first,second)
    if len(segments)<6:raise ValueError('at least six supported frame intersections required')
    folds=[];minimum_condition=1.;minimum_rank=17
    for parity in (0,1):
        totals={name:0. for name in designs};counts=0
        for ix in segments:
            train=ix[first['symbol'][ix]%2==parity];test=ix[first['symbol'][ix]%2!=parity]
            if min(len(train),len(test))<40:continue
            singular=np.linalg.svd(designs['joint'][train],compute_uv=False)
            minimum_condition=min(minimum_condition,float(singular[-1]/singular[0]))
            for name,design in designs.items():
                coefficient,_,rank,_=np.linalg.lstsq(design[train],y[train],rcond=1e-8)
                if name=='joint':minimum_rank=min(minimum_rank,int(rank))
                residual=y[test]-design[test]@coefficient
                totals[name]+=float(np.vdot(residual,residual).real)
            counts+=len(test)
        if not counts:raise ValueError('no complete symbol prediction fold')
        folds.append(dict(parity=parity,samples=counts,squared_prediction_errors=totals,
            improvement_over_first=1-totals['joint']/max(totals['first'],1e-30),
            improvement_over_second=1-totals['joint']/max(totals['second'],1e-30),
            second_exact_vs_control_loss=float(2*counts*np.log(totals['second_control']/max(totals['joint'],1e-30))),
            first_exact_vs_control_loss=float(2*counts*np.log(totals['first_control']/max(totals['joint'],1e-30)))))
    checks=dict(distinct_design=minimum_rank==17 and minimum_condition>1e-5,
        both_components_help_both_heldout_folds=all(min(r['improvement_over_first'],r['improvement_over_second'])>.001 for r in folds),
        exact_secondary_beats_rolled_control=all(r['second_exact_vs_control_loss']>10 for r in folds),
        exact_primary_beats_rolled_control=all(r['first_exact_vs_control_loss']>10 for r in folds))
    return dict(folds=folds,checks=checks,two_received_components_supported=all(checks.values()),
        minimum_training_rank=minimum_rank,minimum_singular_ratio=minimum_condition,
        frame_intersections=len(segments),
        nuisance_channels_fitted_only_on_other_symbols=True,
        CFO_epoch_rate_conditioned_on_whole_probe_RF_fit=True,
        likelihood_differences_are_profile_diagnostics_not_calibrated_probabilities=True,
        distinct_received_components_do_not_prove_distinct_satellite_IDs=True)
