"""58590 cavity/receiver/following-orbit diagnostics; never used for inference."""
from pathlib import Path
import numpy as np
from scipy.optimize import minimize_scalar
from sgp4.api import Satrec
from analyze_dsx01_fixed_site import ecef_states
from leo.sky.propagation import ElementSetCatalogue
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from ds23_frequency_events import make_event_problem
from diagnose_ds23_iteration007_tracks import following
from probe_ds23_worst_association_bottleneck import setup, build
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write

OUT = Path(__file__).resolve().parents[1]
AUDIT = ROOT/'reports/2026_10_22_ds23_dbg01_iteration_001/evidence/DS23-0081/DBG01_audit.json'


def profile(times, values, q, covariance, noise, bank, position):
    inverse = np.linalg.inv(covariance)
    def calc(phase):
        f,e=phase_frequency_grid(bank,times,*latlon(position),phase_seconds=phase)
        residual=values-q*f[0]
        score=float(residual@inverse@residual)
        return score if e.min()>=0 else np.inf,residual,float(e.min())
    grid=np.arange(-15.,15.001,.25)
    scores=[calc(p)[0] for p in grid]
    choices=[(s,p) for s,p in zip(scores,grid,strict=True) if np.isfinite(s)]
    for i in range(1,len(grid)-1):
        if scores[i]<=min(scores[i-1],scores[i+1]):
            r=minimize_scalar(lambda p:calc(p)[0],bounds=(grid[i-1],grid[i+1]),method='bounded')
            choices.append((float(r.fun),float(r.x)))
    score,phase=min(choices)
    _,raw,elevation=calc(phase)
    conditional=noise**2*(inverse@raw)
    assert abs(raw@np.linalg.solve(covariance,raw)-score)<1e-5
    return dict(phase_s=phase,quadratic=score,minimum_elevation_deg=elevation,
        raw_residual_hz=raw,conditional_residual_hz=conditional,
        conditional_rms_hz=float(np.sqrt(np.mean(conditional**2))),raw_rms_hz=float(np.sqrt(np.mean(raw**2))))


def cavity(d,arm,x,reference,target):
    keep=d['keep'].copy()
    for row,sl in zip(d['base'].rows,d['base'].slices,strict=True):
        if row['candidate_norad']==target:keep[sl]=False
    reference=np.array(reference)
    for _ in range(5):
        p=make_event_problem(d['scan'],d['node'],keep,arm,reference,d['powers'],d['means'],d['model'],[])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        change=float(np.max(abs(phase-reference)));reference=phase
    c=p.calculate(x);u=c['features'][keep];g=p.noise_groups[keep]
    w=d['powers'][g]*c['noise_precision'][g]/p.point_noise[keep]**2
    cov=np.linalg.inv(np.diag(c['coefficient_prior_precision'])+u.T@(w[:,None]*u))
    nb=p.hardware.shape[1]+p.smooth.shape[1]
    indices=[];groups=[];members=[];aliases=[]
    for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
        if row['candidate_norad']!=target or not d['keep'][sl].any():continue
        use=d['keep'][sl];t=p.scan.tracks[i];inds=np.arange(len(p.keep))[sl][use]
        indices.extend(inds);groups.extend([len(members)]*len(inds));aliases.append(p.alias[k])
        members.append(dict(component=t['key'],receiver=t['receiver'],channel=t['channel'],points=len(inds),
            observation_ids=np.asarray(t['observation_ids'])[use].tolist()))
    indices=np.array(indices);groups=np.array(groups);noise=p.point_noise[indices]*np.sqrt(2/d['powers'][p.noise_groups[indices]])
    radio=c['features'][indices,:nb];predicted=radio@c['coefficient'][:nb]
    matrix=np.diag(noise**2)+radio@cov[:nb,:nb]@radio.T+300.**2*(groups[:,None]==groups[None,:])
    assert not keep[indices].any()
    return dict(times=p.flat_times[indices],values=p.values[indices]-predicted,q=p.q[indices],
        noise=noise,covariance=matrix,groups=groups,members=members,cavity_phase_change_s=change,
        cavity_radio_prediction_hz=predicted,radio_prediction_sd_hz=np.sqrt(np.diag(radio@cov[:nb,:nb]@radio.T)))


def main():
    d=setup('DS23-0081');target=58590
    native={o['observation_id']:o['measured_cfo_hz'] for o in d['observations']}
    future_path=OUT/'evidence/DS23-0081_following.json'
    if future_path.exists():future=read(future_path)
    else:
        future=following(d,{target});write(future_path,future)
    j=list(d['scan'].norads).index(target)
    causal=dict(time_s=d['scan'].sky['time_s'],position_km=d['scan'].sky['position_km'][[j]],
        velocity_km_s=d['scan'].sky['velocity_km_s'][[j]])
    banks=dict(causal=causal)
    v=future['versions'].get(str(target))
    if v:
        cat=ElementSetCatalogue((str(target),),(target,),(Satrec.twoline2rv(*v['lines']),))
        pos,vel,good=ecef_states(cat,d['scan'].receipt['origin_utc_ns'],causal['time_s'])
        assert good.all()
        banks['following']=dict(causal,position_km=pos,velocity_km_s=vel)
    audit=read(AUDIT);records=[];decomposition=[]
    for arm in ('c0','fitted_c'):
        for location in ('endpoint','diagnostic_point'):
            saved=audit['arms'][arm][location];x=np.array(saved['endpoint_east_north_km'])
            p=build(d,arm,saved['phase_reference']);c=p.calculate(x)
            assert abs(c['negative_twice_elbo']-saved['negative_twice_elbo'])<1e-5
            nb=p.hardware.shape[1];ns=p.smooth.shape[1];nl=len(p.labels);no=3*len(p.supported)
            edges=np.r_[0,np.cumsum([nb,ns,nl,no,len(p.members)])]
            contributions={name:c['features'][:,a:b]@c['coefficient'][a:b]
                for name,a,b in zip(('radio','smooth','phase','orbit','fragment'),edges[:-1],edges[1:],strict=True)}
            for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
                use=d['keep'][sl]
                if not use.any():continue
                t=p.scan.tracks[i]
                decomposition.append(dict(arm=arm,location=location,norad=row['candidate_norad'],component=t['key'],
                    receiver=t['receiver'],channel=t['channel'],times=t['times'][use],
                    native_values_hz=np.array([native[oid] for oid in t['observation_ids']])[use],
                    graph_alias_gauge_values_hz=t['values'][use],conditional_residual_hz=c['conditional_residual_hz'][sl][use],
                    contributions_hz={n:a[sl][use] for n,a in contributions.items()}))
            data=cavity(d,arm,x,saved['phase_reference'],target)
            for version,bank in banks.items():
                shared=profile(data['times'],data['values'],data['q'],data['covariance'],data['noise'],bank,x)
                partitions=[]
                for group in range(len(data['members'])):
                    ix=np.flatnonzero(data['groups']==group)
                    fitted=profile(data['times'][ix],data['values'][ix],data['q'][ix],data['covariance'][np.ix_(ix,ix)],
                        data['noise'][ix],bank,x)
                    residual=shared['conditional_residual_hz'][ix]
                    partitions.append(dict(member=data['members'][group],times=data['times'][ix],independent_phase_fit=fitted,
                        shared_phase_residual_hz=residual,shared_phase_rms_hz=float(np.sqrt(np.mean(residual**2))),
                        shared_phase_noise={k:v[0] for k,v in batch_noise_screen(residual[None,:],data['times'][ix]).items()}))
                records.append(dict(arm=arm,location=location,position=x,version=version,shared=shared,tracks=partitions,
                    times=data['times'],groups=data['groups'],radio_prediction_sd_hz=data['radio_prediction_sd_hz'],
                    cavity_phase_change_s=data['cavity_phase_change_s']))
                print(arm,location,version,'phase',round(shared['phase_s'],4),'RMS',round(shared['conditional_rms_hz'],3),flush=True)
    write(OUT/'evidence/family_58590.json',dict(records=records,decomposition=decomposition,
        target_selected_from_previous_largest_family_ablation=True,
        family_excluded_from_receiver_calibration=True,curved_only_190_points=True,
        predictive_11_points_omitted_from_this_diagnostic=True,
        following_TLE_diagnostic_only_not_inference=True,following_available=v is not None,
        frozen_locations_and_original_aliases=True,phase_without_prior_in_both_TLE_versions=True,
        satellite_shape_modes_omitted_in_both_profile_versions=True,
        correlated_receiver_and_300Hz_fragment_covariance_retained=True,
        no_position_or_identity_changes=True))


if __name__=='__main__':main()
