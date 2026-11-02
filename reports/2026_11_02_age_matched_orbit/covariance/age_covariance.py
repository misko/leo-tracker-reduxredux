"""Age-matched, phase-separated causal TLE revision covariance; report only."""
from __future__ import annotations
import copy
from functools import lru_cache
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parents[1]/'2026_11_02_generalized_corrections/covariance/causal_covariance.py'
OLD_SHA='04c63abf99a198bb0cd5352db7f96334800f1baf3e6524287f8a5bf4fa43ef32'
if hashlib.sha256(OLD.read_bytes()).hexdigest()!=OLD_SHA:raise ValueError('Frozen prior covariance helpers changed')
spec=importlib.util.spec_from_file_location('frozen_covariance_helpers',OLD)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

POLICY=dict(version='age-matched-revision-v1',maximum_age_hours=72,
    horizon_tolerance_hours=2.,horizon_relative_tolerance=.25,
    minimum_pairs_primary=3,minimum_pairs_exploratory=2,
    older_available_by_target_epoch=True,zero_mean=True,shrinkage_to_identity=.5,
    covariance_eigenvalue_bounds=[1.,16.],minimum_represented_energy_fraction=.5,
    alignment_maximum_steps=8,alignment_tolerance_s=1e-7,maximum_alignment_s=120.,
    matching='maximum nonreused-element cardinality, minimum total absolute horizon mismatch, stable epoch/hash tie',
    transport='historical newer-epoch physical derivatives, solve rev/day and degrees, divide current declared physical SDs; no historical-state/current-geometry projection')


def sha(path):return base.sha(path)


def select_pairs(raw,nominal,cutoff,origin,family,horizon_hours,*,require_forecast=True):
    """Receipt validation precedes deterministic age-only disjoint matching."""
    _,provenance=base.validate_and_select(raw,nominal,cutoff,origin,family)
    oldest=cutoff-int(POLICY['maximum_age_hours']*3.6e12)
    nominal_epoch=base.tle_epoch(nominal['lines'])
    unique={}
    for row in raw['past_versions'].get(str(family),[]):
        if not (oldest<=row['epoch']<=nominal_epoch and oldest<=row['collected_utc_ns']<=cutoff):continue
        key=(row['collected_utc_ns'],base.element_sha(row['lines']))
        if row['epoch'] not in unique or key<(unique[row['epoch']]['collected_utc_ns'],base.element_sha(unique[row['epoch']]['lines'])):
            unique[row['epoch']]=row
    versions=sorted(unique.values(),key=lambda r:(r['epoch'],base.element_sha(r['lines'])))
    tolerance=max(POLICY['horizon_tolerance_hours'],POLICY['horizon_relative_tolerance']*horizon_hours)
    edges={}
    for i,older in enumerate(versions):
        for j,newer in enumerate(versions[i+1:],i+1):
            horizon=(newer['epoch']-older['epoch'])/3.6e12
            error=abs(horizon-horizon_hours)
            if error<=tolerance and (not require_forecast or older['collected_utc_ns']<=newer['epoch']):
                edges[i,j]=dict(older=older,newer=newer,horizon_hours=horizon,absolute_horizon_error_hours=error)
    @lru_cache(None)
    def solve(mask):
        if not mask:return ()
        i=(mask&-mask).bit_length()-1;remaining=mask^(1<<i)
        options=[solve(remaining)]
        for j in range(i+1,len(versions)):
            if (i,j) in edges and remaining&(1<<j):options.append(((i,j),)+solve(remaining^(1<<j)))
        return min(options,key=lambda pairs:(-len(pairs),sum(edges[p]['absolute_horizon_error_hours'] for p in pairs),pairs))
    selected=[edges[p] for p in solve((1<<len(versions))-1)]
    return selected,dict(provenance,eligible_versions=len(versions),eligible_pair_count=len(edges),
        maximum_nonreused_pair_count=len(selected),pair_count=len(selected),nominal_horizon_hours=horizon_hours,
        horizon_tolerance_hours=tolerance,forecast_availability_required=require_forecast)


def physical_bank(satellite,origin,times,anchor_s,scales):
    """Physical n/i/RAAN derivatives with mean longitude held at anchor UTC."""
    from analyze_dsx01_fixed_site import ecef_states
    from fit_s01_69333_tle_parameter import perturb
    from prototype_dsx01_mean_motion import reference_motion_satellite
    from leo.sky.propagation import ElementSetCatalogue
    elapsed=(origin/1e9+anchor_s)/86400+2440587.5-satellite.jdsatepoch-satellite.jdsatepochF
    satellites=[]
    for mode in range(3):
        for step in (.001,-.001):
            satellites.append(reference_motion_satellite(satellite,step,elapsed) if mode==0 else
                perturb(satellite,('inclination_deg','raan_deg')[mode-1],step))
    cat=ElementSetCatalogue((str(satellite.satnum),)*6,(int(satellite.satnum),)*6,tuple(satellites))
    p,v,valid=ecef_states(cat,origin,np.asarray(times))
    if not valid.all():raise ValueError('Physical derivative propagation failed')
    return dict(time_s=np.asarray(times),position_km=(p[::2]-p[1::2])/.002*np.asarray(scales)[:,None,None],
                velocity_km_s=(v[::2]-v[1::2])/.002*np.asarray(scales)[:,None,None])


def project_pair(pair,duration_s,current_scales):
    """Infer historical physical parameter revision at the newer TLE epoch."""
    from sgp4.api import Satrec
    from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
    newer,older=pair['newer'],pair['older'];origin=newer['epoch']
    times=np.array([-duration_s/2,0.,duration_s/2])
    nsat=Satrec.twoline2rv(*newer['lines']);osat=Satrec.twoline2rv(*older['lines'])
    p,v=base._phase_states(nsat,origin,times)
    inertial=v.copy();inertial[:,0]-=EARTH_ROTATION_RAD_S*p[:,1];inertial[:,1]+=EARTH_ROTATION_RAD_S*p[:,0]
    tau=float(np.median(np.linalg.norm(p,axis=1)/np.linalg.norm(inertial,axis=1)))
    target=base._vector(p,v,tau)
    plus=base._vector(*base._phase_states(nsat,origin,times,.01),tau)
    minus=base._vector(*base._phase_states(nsat,origin,times,-.01),tau)
    phase_direction=(plus-minus)/.02;phase_direction/=np.linalg.norm(phase_direction)
    projector=np.eye(len(target))-np.outer(phase_direction,phase_direction)
    bank=physical_bank(nsat,origin,times,0.,current_scales)
    design=projector@np.array([base._vector(bank['position_km'][i],bank['velocity_km_s'][i],tau) for i in range(3)]).T
    column_norm=np.linalg.norm(design,axis=0)
    if not np.isfinite(column_norm).all() or np.any(column_norm<=1e-14):
        raise ValueError('Historical physical basis has a zero or nonfinite column')
    singular=np.linalg.svd(design/column_norm,compute_uv=False)
    if not np.isfinite(singular).all() or singular[-1]<singular[0]*1e-8:raise ValueError('Historical physical basis rank insufficient')
    phase=0.;converged=False
    for iteration in range(POLICY['alignment_maximum_steps']):
        value=base._vector(*base._phase_states(osat,origin,times,phase),tau)
        hi=base._vector(*base._phase_states(osat,origin,times,phase+.01),tau)
        lo=base._vector(*base._phase_states(osat,origin,times,phase-.01),tau)
        derivative=(hi-lo)/.02;step=-float((value-target)@derivative/(derivative@derivative));phase+=step
        if abs(phase)>POLICY['maximum_alignment_s']:raise ValueError('Historical phase alignment exceeds bound')
        if abs(step)<POLICY['alignment_tolerance_s']:converged=True;break
    if not converged:raise ValueError('Historical phase alignment failed convergence')
    delta=projector@(base._vector(*base._phase_states(osat,origin,times,phase),tau)-target)
    normalized=np.linalg.lstsq(design/column_norm,delta,rcond=1e-8)[0]
    coefficients=normalized/column_norm
    residual=delta-design@coefficients
    def receipt(row):return dict(element_sha256=base.element_sha(row['lines']),epoch_utc_ns=row['epoch'],
        collected_utc_ns=row['collected_utc_ns'],snapshot_sha256=row['snapshot_sha256'])
    return coefficients,dict(older=receipt(older),newer=receipt(newer),
        horizon_hours=pair['horizon_hours'],absolute_horizon_error_hours=pair['absolute_horizon_error_hours'],
        physical_parameter_revision=(coefficients*np.asarray(current_scales)).tolist(),
        physical_parameter_units=['rev/day','deg','deg'],coefficients=coefficients.tolist(),
        current_mode_SD=list(map(float,current_scales)),historical_derivative_anchor_utc_ns=origin,
        historical_arc_times_s=times.tolist(),column_normalized_singular_values=singular.tolist(),
        column_norms=column_norm.tolist(),phase_alignment_s=phase,alignment_converged=converged,
        alignment_steps=iteration+1,final_alignment_step_s=step,orbital_velocity_timescale_s=tau,
        phase_removed_state_energy_km2=float(delta@delta),projection_residual_energy_km2=float(residual@residual))


def make_covariance(scan,base_problem,z,family,receipt_sink=None):
    native=Path(z['native_path']);history=native.parent/'causal_phase_history'/(native.name+'.json')
    nominal_path=native/'nominal_elements.json';observations=native/'observations.json'
    raw=json.loads(history.read_text());nominal=scan.elements[str(family)]
    if raw['latest_elements_sha256']!=sha(nominal_path):raise ValueError('History/nominal file hash differs')
    if nominal['lines']!=json.loads(nominal_path.read_text())[str(family)]['lines']:raise ValueError('Nominal target differs')
    timestamps=np.array([r['time_s'] for r in json.loads(observations.read_text())],float)
    duration=float(timestamps.max()-timestamps.min());mid=float((timestamps.max()+timestamps.min())/2)
    horizon=(scan.receipt['origin_utc_ns']+int(round(mid*1e9))-base.tle_epoch(nominal['lines']))/3.6e12
    pairs,info=select_pairs(raw,nominal,z['scan_receipt']['cutoff_utc_ns'],scan.receipt['origin_utc_ns'],family,horizon)
    receipt=dict(info,history_path=str(history),history_sha256=sha(history),nominal_elements_path=str(nominal_path),
        nominal_elements_sha256=sha(nominal_path),temporal_extent_path=str(observations),temporal_extent_sha256=sha(observations),
        historical_arc_duration_s=duration,common_native_midpoint_s=mid,
        primary_history_eligible=len(pairs)>=POLICY['minimum_pairs_primary'],
        exploratory_history_eligible=len(pairs)>=POLICY['minimum_pairs_exploratory'])
    if receipt_sink is not None:receipt_sink.update(receipt)
    if len(pairs)<POLICY['minimum_pairs_exploratory']:return None,dict(receipt,reason='fewer than two nonreused age-matched causal forecast revisions')
    j=next(j for j in base_problem.labels if int(scan.norads[j])==family)
    if j not in base_problem.supported:return None,dict(receipt,reason='target lacks three existing supported modes')
    metadata=base_problem.mode_metadata[j]
    scales=[metadata[k] for k in ['mean_motion_sigma_rev_day','inclination_sigma_deg','raan_sigma_deg']]
    from sgp4.api import Satrec
    sat=Satrec.twoline2rv(*nominal['lines'])
    local=base_problem.labels.index(j)
    direct=physical_bank(sat,scan.receipt['origin_utc_ns'],base_problem.mode_bank['time_s'],150.,scales)
    differences={key:float(np.max(abs(direct[key]-base_problem.mode_bank[key][3*local:3*local+3]))) for key in ['position_km','velocity_km_s']}
    if max(differences.values())>1e-10:raise ValueError('Current physical coordinate map does not reproduce existing mode bank')
    coefficients=[];details=[]
    for pair in pairs:
        a,detail=project_pair(pair,duration,scales);coefficients.append(a);details.append(detail)
    energy=sum(r['phase_removed_state_energy_km2'] for r in details)
    remaining=sum(r['projection_residual_energy_km2'] for r in details)
    represented=1-remaining/max(energy,1e-30)
    receipt.update(current_mode_SD=scales,current_mode_metadata=metadata,current_nominal_inclination_deg=float(np.rad2deg(sat.inclo)),
        current_nominal_radius_km=float(1.5*(sat.no_kozai*1440/(2*np.pi))*metadata['radial_sigma_km']/metadata['mean_motion_sigma_rev_day']),
        current_derivative_anchor_s=150.,current_mode_direct_perturbation_max_difference=differences,
        historical_pair_projections=details,represented_energy_fraction=represented)
    if represented<POLICY['minimum_represented_energy_fraction']:return None,dict(receipt,reason='age-matched revisions poorly represented by existing physical coordinates')
    covariance,summary=base.shrunk_covariance(coefficients)
    receipt.update(summary,coefficient_covariance=covariance.tolist(),reason='age-matched physical revision covariance supported')
    return covariance,receipt


def candidate_context(d,z,metadata):
    """Return (context, receipt); no fitting, RF residuals or evaluation labels."""
    family=int(metadata['selected_family'])
    receipt=dict(policy=POLICY,selected_family=family,status='fallback',applied=False,added_columns=0,
        RF_or_GPS_used_for_covariance=False,prior_helper_sha256=OLD_SHA)
    try:
        problem=d['problems']['fitted_c'][0]
        covariance,details=make_covariance(d['scan'],problem,z,family,receipt);receipt.update(details)
        if covariance is None:return d,receipt
        from probe_ds23_history_calibrated_phase import make_problem
        original=d.get('problem_factory',make_problem)
        def factory(scan,node,keep,arm,reference,powers,means,multiplier,nu):
            p=original(scan,node,keep,arm,reference,powers,means,multiplier,nu)
            j=next(j for j in p.labels if int(scan.norads[j])==family)
            if j not in p.supported:raise ValueError('Target orbital support changed')
            p.mode_bank=base.transform_mode_bank(p.mode_bank,p.labels.index(j),covariance)
            p.mode_metadata=copy.deepcopy(p.mode_metadata);p.mode_metadata[j]['age_matched_covariance']=covariance.tolist()
            return p
        receipt.update(status='ready',applied=True)
        return dict(d,problem_factory=factory,problems=dict(d['problems'])),receipt
    except (ValueError,KeyError,OSError) as exc:
        return d,dict(receipt,reason=str(exc))
