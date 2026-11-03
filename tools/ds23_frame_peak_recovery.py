"""Recover distinct native peaks through repeated simultaneous frame matches.

No position, TLE or satellite identity enters measurement selection. A later
inference experiment may nominate each recovered curved fragment to its
already-curved anchor's satellite. Original retained measurements are excluded
and additional native peaks have explicit, separate research identities.
"""

from collections import Counter, defaultdict
import hashlib
import json

import numpy as np

from ds23_frame_registration import PERIOD, wrap
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def polynomial_screen(times, values, sigma, *, require_curvature=True):
    t, y, noise = (np.asarray(v, float) for v in (times, values, sigma))
    if len(t) < 8 or np.ptp(t) < (20 if require_curvature else 6) or np.any(np.diff(t) <= 0):
        return None
    x = (t-t.mean())/(np.ptp(t)/2)
    choices=[]
    for degree in range(1, min(4, len(t)//4-1)+1):
        design=np.polynomial.legendre.legvander(x, degree)
        coefficient=np.linalg.lstsq(design/noise[:,None], y/noise, rcond=None)[0]
        residual=y-design@coefficient
        cost=float(np.sum((residual/noise)**2)+(degree+1)*np.log(len(t)))
        choices.append(dict(degree=degree, coefficients_hz=coefficient,
            reference_time_s=float(t.mean()),time_scale_s=float(np.ptp(t)/2),
            residual_hz=residual, BIC=cost))
    best=min(choices,key=lambda r:(r['BIC'],r['degree']))
    # Curvature must be supported by the observations, rather than by choosing
    # a higher polynomial degree for a mostly linear or noisy fragment.
    linear_rms=float(np.sqrt(np.mean(choices[0]['residual_hz']**2)))
    diagnostics={k:v[0] for k,v in batch_noise_screen(best['residual_hz'][None],t).items()}
    rms=float(np.sqrt(np.mean(best['residual_hz']**2)))
    curved=bool(np.ptp(t)>=20 and best['degree']>=2
        and choices[0]['BIC']-best['BIC']>=10 and linear_rms>=250)
    if ((require_curvature and not curved) or rms>450 or not diagnostics['noise_screen_pass']):
        return None
    return dict(best, linear_residual_rms_hz=linear_rms,
        curvature_BIC_gain=choices[0]['BIC']-best['BIC'],residual_rms_hz=rms,
        diagnostics=diagnostics,active_curvature=curved)


def measurement_id(case, receiver, channel, rf_hz, time_s, peak):
    payload=[case,receiver,channel,float(rf_hz),round(time_s,9),
             round(peak['epoch'],6),round(float(wrap(peak['cfo'])),1)]
    return 'native-frame:'+hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest()


def select_recoveries(case, anchor_tracks, observations, pairs, occupied_ids, noise_metadata,
                      *, include_secondary, require_curvature=True):
    """Use only active curved anchors and never reuse a retained measurement.

    anchor_tracks map component keys to active arrays, with CFO values lifted
    on each original track's branch. Peak ownership is resolved before fitting;
    a peak nominated by different curved anchors is rejected as ambiguous.
    """
    observation_lookup={(o['receiver'],round(o['time_s'],6),float(o['actual_rf_hz'])):o
                        for o in observations}
    candidates=[];rejected=Counter()
    for pair in pairs:
        for component in pair['curved_anchor_components']:
            if component not in anchor_tracks:
                continue
            anchor=anchor_tracks[component];rx=anchor['receiver'];target_rx=3-rx
            times=np.asarray(anchor['times']);ix=int(np.argmin(abs(times-pair['time_s'])))
            if abs(times[ix]-pair['time_s'])>1e-6:
                continue
            source=pair['first' if rx==1 else 'second']
            target=pair['second' if rx==1 else 'first']
            if abs(wrap(anchor['values'][ix]-source['cfo']))>1.:
                rejected['source_native_peak_does_not_match_anchor_measurement']+=1
                continue
            rf=float(pair['rf_hz']);time_s=float(pair['time_s'])
            primary=observation_lookup.get((target_rx,round(time_s,6),rf))
            separation=(float(abs(wrap(target['cfo']-primary['measured_cfo_hz'])))
                        if primary is not None else None)
            is_primary=primary is not None and separation<250
            if is_primary:
                oid=primary['observation_id'];cfo=primary['measured_cfo_hz']
                if oid in occupied_ids:
                    rejected['already_retained_original_winner']+=1;continue
                kind='unretained_original_winner'
            else:
                if not include_secondary:
                    rejected['secondary_not_in_winner_only_arm']+=1;continue
                if separation is not None and separation<1500:
                    rejected['unresolved_neighboring_native_peak']+=1;continue
                oid=measurement_id(case,target_rx,pair['channel'],rf,time_s,target)
                cfo=target['cfo'];kind='additional_native_peak'
            value=float(anchor['values'][ix]+wrap(cfo-source['cfo']))
            sigma=float(noise_metadata['constant_radio_sigma_hz'])
            if noise_metadata['extra_parameter_BIC_gain']>0:
                variance=noise_metadata['floor_sigma_hz']**2+noise_metadata['strength_hz2']/max(target['margin'],1e-6)
                sigma=max(sigma,float(np.sqrt(np.clip(variance,40**2,600**2))))
            candidates.append(dict(component=component,receiver=target_rx,channel=pair['channel'],
                rf_hz=rf,time_s=time_s,value=value,observation_id=oid,kind=kind,
                sigma_hz=max(150.,sigma),source_observation_id=anchor['observation_ids'][ix],
                source_peak=source,target_peak=target,visit_index=pair['visit_index'],
                frame_epoch_difference_samples=pair['epoch_difference_samples']))
    owners=defaultdict(set)
    for row in candidates:
        owners[row['observation_id']].add(row['component'])
    unique={}
    for row in candidates:
        oid=row['observation_id']
        if len(owners[oid])>1:
            rejected['ambiguous_multiple_curved_anchors']+=1;continue
        if oid in unique:
            continue
        unique[oid]=row
    groups=defaultdict(list)
    for row in unique.values():
        groups[row['component'],row['receiver']].append(row)
    fragments=[];fragment_inventory=[]
    for (parent,receiver),rows in sorted(groups.items()):
        rows.sort(key=lambda r:r['time_s'])
        t=np.array([r['time_s'] for r in rows])
        # Never bridge a long gap to manufacture a new curved calibration arc.
        for number,index in enumerate(np.split(np.arange(len(rows)),np.flatnonzero(np.diff(t)>10)+1)):
            subset=[rows[k] for k in index]
            times=np.array([r['time_s'] for r in subset]);values=np.array([r['value'] for r in subset])
            sigma=np.array([r['sigma_hz'] for r in subset])
            screen=polynomial_screen(times,values,sigma,require_curvature=require_curvature)
            fragment_inventory.append(dict(parent=parent,receiver=receiver,points=len(subset),
                span_s=float(np.ptp(times)),passed=screen is not None))
            if screen is None:
                rejected['fragment_without_supported_clean_curvature']+=len(subset);continue
            key=f'{parent}-FRAME-RX{receiver}-F{number:02d}'
            fragments.append(dict(key=key,parent_component=parent,receiver=receiver,
                channel=subset[0]['channel'],rf_hz=subset[0]['rf_hz'],
                times=times,values=values,observation_ids=[r['observation_id'] for r in subset],
                sigma_hz=sigma,peak_ownership=subset,polynomial=screen))
    ids=[oid for f in fragments for oid in f['observation_ids']]
    if len(set(ids))!=len(ids) or set(ids)&set(occupied_ids):
        raise ValueError('recovered measurements have duplicate retained owners')
    return fragments,dict(rejected=dict(rejected),candidate_distinct_measurements=len(unique),
        fragment_inventory=fragment_inventory,
        added_original_winners=sum(r['kind']=='unretained_original_winner' for f in fragments for r in f['peak_ownership']),
        added_native_secondary_peaks=sum(r['kind']=='additional_native_peak' for f in fragments for r in f['peak_ownership']))
