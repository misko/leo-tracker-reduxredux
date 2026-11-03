"""Extract causal TEME along-track states; no receiver or observer coordinate."""

from collections import Counter
import numpy as np
from sgp4.api import Satrec

from leo.sky.frames import julian_day_from_utc_ns


def state(satellite,utc_ns):
    jd,fr=julian_day_from_utc_ns(np.array([utc_ns]))
    code,p,v=satellite.sgp4(float(jd[0]),float(fr[0]))
    if code:raise ValueError('SGP4 state unavailable')
    return np.asarray(p),np.asarray(v)


def phase(current,reference,utc_ns):
    p,v=state(current,utc_ns);p0,v0=state(reference,utc_ns)
    norm=float(v0@v0)
    if not norm>0:raise ValueError('invalid reference velocity')
    return float((p-p0)@v0/norm),float(v@v0/norm)


def observation(current,reference,utc_ns):
    value,_=phase(current,reference,utc_ns)
    plus,_=phase(current,reference,utc_ns+1_000_000_000)
    minus,_=phase(current,reference,utc_ns-1_000_000_000)
    return [value,(plus-minus)*1800.]


def transported_observation(current,previous,reference,utc_ns):
    """Transport the original current-minus-previous phase measurement.

    This preserves the exact original scalar validation target and its affine
    Jacobian. Projection into a single phase state is an approximation; retain
    its discrepancy from direct projection as a separately auditable quantity.
    """
    def value(t):
        base,factor=phase(previous,reference,t)
        delta,_=phase(current,previous,t)
        return base+factor*delta
    y=value(utc_ns)
    rate=(value(utc_ns+1_000_000_000)-value(utc_ns-1_000_000_000))*1800.
    direct,_=phase(current,reference,utc_ns)
    return [y,rate],abs(y-direct)


def extract(history,forecast,elements):
    cutoff=history['cutoff_utc_ns'];target=history['origin_utc_ns']+150_000_000_000
    rows={(r['norad'],r['validation_time_ns']):r for r in forecast['transitions']}
    series=[];rejected=Counter()
    for number,raw in history['past_versions'].items():
        if any(max(v['epoch'],v['collected_utc_ns'])>cutoff for v in raw):
            raise ValueError('future TLE in state-filter history')
        if str(number) not in elements:
            rejected['no_current_nominal_element']+=1;continue
        nominal=elements[str(number)];provenance=nominal['provenance']
        if max(provenance['element_epoch_utc_ns'],provenance['collected_utc_ns'])>cutoff:
            raise ValueError('future nominal TLE in state-filter prediction')
        versions=[]
        for v in raw:
            if v['epoch']>v['collected_utc_ns']:
                rejected['element_published_before_its_epoch']+=1;continue
            if versions and (v['epoch']<=versions[-1]['epoch'] or v['collected_utc_ns']<=versions[-1]['collected_utc_ns']):
                rejected['nonincreasing_version']+=1;continue
            versions.append(v)
        if len(versions)<3:
            rejected['fewer_than_three_versions']+=1;continue
        try:
            satellites=[Satrec.twoline2rv(*v['lines']) for v in versions]
            reference=satellites[0];origin=versions[0]['collected_utc_ns']
            values=[];times=[];eligible=[];baseline=[];transport_errors=[]
            for k,(v,satellite) in enumerate(zip(versions,satellites,strict=True)):
                utc=v['collected_utc_ns']
                value,error=(transported_observation(satellite,satellites[k-1],reference,utc) if k else
                             (observation(satellite,reference,utc),0.))
                values.append(value);transport_errors.append(error);times.append((utc-origin)/3.6e12)
                row=rows.get((int(number),utc)) if k>=2 else None
                # The original predictor uses the immediately preceding two
                # elements. Reject mismatches rather than change its inputs.
                if row and (abs(row['age_s']-(utc-versions[k-1]['epoch'])/1e9)>1e-4 or
                            abs(row['epoch_gap_s']-(versions[k-1]['epoch']-versions[k-2]['epoch'])/1e9)>1e-4):
                    row=None
                eligible.append(row is not None)
                if row:
                    nominal_phase,factor=phase(satellites[k-1],reference,utc)
                    if factor<=0:raise ValueError('phase coordinates reverse direction')
                    baseline.append(dict(row,nominal_reference_phase_s=nominal_phase,phase_coordinate_factor=factor))
                else:baseline.append(None)
            current=Satrec.twoline2rv(*nominal['lines'])
            nominal_phase,factor=phase(current,reference,target)
            if factor<=0:raise ValueError('phase coordinates reverse direction')
            series.append(dict(norad=int(number),times_hours=times,observations=values,
                score_eligible=eligible,publication_utc_ns=[v['collected_utc_ns'] for v in versions],
                baseline_transitions=baseline,target_hours=(target-origin)/3.6e12,
                RF_nominal_reference_phase_s=nominal_phase,RF_phase_coordinate_factor=factor,
                reference_collection_utc_ns=origin,reference_epoch_utc_ns=versions[0]['epoch']))
            series[-1]['maximum_phase_transport_discrepancy_s']=max(transport_errors)
        except ValueError as exc:
            rejected[str(exc)]+=1
    return dict(case=history['case'],series=series,rejected=dict(rejected),cutoff_utc_ns=cutoff,
        RF_prediction_utc_ns=target,reference_is_first_available_TLE=True,
        target_TLE_never_used_to_predict_itself=True,
        phase_target_matches_original_by_affine_transport=True,
        no_RF_GPS_or_observer_geometry_used=True,
        along_track_linear_state_is_a_model_hypothesis_not_true_orbit=True)
