"""Recompute the existing support heuristic using training observations only."""
import numpy as np
from evaluate_ds23_family_weighting import family_weights
from probe_algo01_0217_improvements import candidate_profile,competitor_confidence
from investigate_ds23_adaptive_failures import phase_widths
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency


def training_profile(track,active,frequency,derivative,elevation,radio,widths):
    """Slice before scoring; excluded values cannot enter candidate confidence."""
    use=np.asarray(active,bool);q=track['rf_hz']/11.5e9
    if use.shape!=np.asarray(track['values']).shape or use.sum()<4:raise ValueError('at least four training points required')
    y=np.asarray(track['values'])[use]-np.asarray(radio)[use]
    return candidate_profile(y,q*np.asarray(frequency)[:,use],q*np.asarray(derivative)[:,use],
        np.asarray(elevation)[:,use],150.,widths)


def learn(p,x,original_powers):
    """A c=0 training pilot nominates weights shared by both c arms/variants.

    This deliberately retains the legacy heuristic, including power one for
    two-receiver families. Its soft catalogue score is not a probability of
    identity correctness. Physical orbital modes are absent from this screen.
    """
    state=p.state(x);scan=p.scan;widths,_=phase_widths(scan,list(range(len(scan.norads))))
    anchors=[np.asarray(x)]+[np.clip(np.asarray(x)+delta,-12.5,12.5) for delta in
        (np.array([2.,0.]),np.array([-2.,0.]),np.array([0.,2.]),np.array([0.,-2.]))]
    weights=[];records=[];counts=[int(p.keep[sl].sum()) for sl in p.slices]
    radio=[]
    for i in p.members:
        t=scan.tracks[i];q=t['rf_hz']/11.5e9
        radio.append(scan.hardware(t,state['beta'])+q*scan.rx_basis[i]@state['smooth'][t['receiver']-1])
    for anchor in anchors:
        f,e,derivative=phase_linear_frequency(scan.geometry,*latlon(anchor));confidence=[]
        for row,i,sl,correction in zip(p.rows,p.members,p.slices,radio,strict=True):
            active=p.keep[sl]
            if active.sum()<4:confidence.append(0.);continue
            ix=scan.index[i];profile=training_profile(scan.tracks[i],active,f[:,ix],derivative[:,ix],e[:,ix],correction,widths)
            j=row['candidate_index'];cost=profile['cost'];finite=np.isfinite(cost)
            if not finite.any():value=0.;margin=None;winner=None
            else:
                value,margin=competitor_confidence(cost,j);winner=int(scan.norads[np.argmin(cost)])
                if not np.isfinite(margin):margin=None
            confidence.append(value);records.append(dict(component=row['component'],anchor_east_north_km=anchor,
                norad=int(scan.norads[j]),screen_winner=winner,conditional_confidence=value,competitor_margin=margin,
                training_points=int(active.sum()),observation_ids=np.asarray(scan.tracks[i]['observation_ids'])[active]))
        weights.append(confidence)
    confidence=np.min(weights,axis=0)
    power,owners,_=family_weights(p.rows,p.members,scan.tracks,confidence,'cross_rx_support',counts)
    curves=[dict(component=row['component'],norad=row['candidate_norad'],training_points=n,
        minimum_confidence=float(c),training_power=float(w),original_full_data_power=float(old),
        receiver_channel_owners=sorted(owners[row['candidate_index']]))
        for row,n,c,w,old in zip(p.rows,counts,confidence,power,original_powers,strict=True)]
    return power,dict(powers=power,curves=curves,screens=records,anchors=anchors,
        calibration='c0 unit-power training-only curved pilot',same_weights_in_both_c_arms=True,
        noise_hz=150.,native_not_used=True,held_values_not_used=True,
        conditional_on_frozen_graph_identities_and_priors=True,
        screen_omits_physical_orbit_modes=True,confidence_is_not_calibrated_probability=True)
