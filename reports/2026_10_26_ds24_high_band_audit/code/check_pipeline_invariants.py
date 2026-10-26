"""Bounded, read-only DS24 audit. No context() call, fit(), or RF access.

Run from the repository:
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=src:tools .venv/bin/python /srv/bulk/leo/research/ds24-high-band-audit-20261026/code/check_pipeline_invariants.py
"""
import copy
import hashlib
import itertools
import json
from pathlib import Path
import time

import numpy as np

from algo02_scan import load_scan
import analyze_dsx01_fixed_site as matching
from ds23_frequency_events import make_event_problem, attach_event_predictive
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics, proposal_phases
from leo.analysis.research.retained_track_likelihood import PERIOD
from prototype_dsx01_continuous_position import CENTER
from prototype_dsx01_calibration_modes import project_radio_state
from run_dsx01_clean_region import zero_state

ROOT = Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')
OUT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def flipped(scan):
    result = copy.copy(scan)
    result.tracks = [dict(t, channel=t['channel'] + (4 if t['channel'] <= 4 else -4)) for t in scan.tracks]
    result.groups = [(result.tracks[i]['key'], [result.tracks[i]]) for i in result.curved]
    return result


def seed_check(scan, other):
    """Exactly the proposal-statistics path in fresh_discovery; no refinement."""
    base = phase_linear_frequency(scan.geometry, *CENTER)
    def seeds(view):
        stats = matching.statistics(view.groups,
            dict(time_s=view.times, doppler_0=base[0], elevation_deg=base[1]),
            {str(t['channel']): 0. for t in view.tracks})
        stats = augment_phase_statistics(stats, view.times, base[0], base[2])
        phases, _ = proposal_phases(stats, np.zeros(8), view.sigma,
            np.full(len(view.norads), 15.), return_components=True)
        phi = phases[stats['ci']]
        modified = dict(stats, mean=stats['mean']-stats['hm']*phi,
            xz=stats['xz']-stats['xh']*phi,
            rss=np.maximum(0, stats['rss']-2*stats['zh']*phi+stats['hh']*phi**2))
        shape=np.maximum(0,modified['rss']-modified['xz']**2/np.maximum(stats['xx'][:,None],1e-12))
        modified['shape_rms']=np.sqrt(np.add.reduceat(shape,stats['starts'],axis=0)/stats['count'][:,None])
        return list(itertools.islice(matching.seed_calibrations(modified,np.zeros(8),4),4))
    a, b = seeds(scan), seeds(other)
    assert len(a) == len(b)
    order = [1,0,3,2,5,4,7,6]
    raw = max(float(np.max(abs(x[order]-y))) for x,y in zip(a,b,strict=True))
    projected = 0.
    for x,y in zip(a,b,strict=True):
        sa,sb=zero_state(scan),zero_state(other);sa['beta']=x;sb['beta']=y
        pa,pb=project_radio_state(sa)['beta'],project_radio_state(sb)['beta']
        projected=max(projected,float(np.max(abs(pa[order]-pb))))
    assert raw < 1e-8 and projected < 1e-8
    return dict(seeds=len(a),raw_max_beta_difference_hz=raw,projected_max_beta_difference_hz=projected)


def replay(subset, case):
    root=ROOT/subset
    saved=read(root/'family_cavity/position'/f'{case}.json')
    selected=saved.get('selected') if saved['accepted'] else None
    node=selected['node'] if selected else saved['baseline_node']
    means=np.asarray(selected['means'] if selected else saved['baseline_means'])
    entries=selected['entries'] if selected else saved['baseline_entries']
    keep=np.asarray(saved['original_mask'],bool);powers=np.asarray(saved['powers'])
    scan=load_scan(root,case);other=flipped(scan)
    result=dict(subset=subset,case=case,seeds=seed_check(scan,other),arms={})
    for arm, record in saved['policy_arms'].items():
        x=np.asarray(record['endpoint_east_north_km']);reference=np.asarray(record['phase_reference'])
        def build(view):
            p=make_event_problem(view,node,keep,arm,reference,powers,means,saved['model'],[])
            attach_event_predictive(p,entries,powers)
            return p
        p,pf=build(scan),build(other);c,cf=p.calculate(x),pf.calculate(x)
        nb=p.hardware.shape[1]
        permutation=np.arange(c['features'].shape[1]);permutation[:4]=[1,0,3,2]
        sign=np.ones(len(permutation));sign[[5,7]]=-1
        design_error=float(np.max(abs(c['features']-cf['features'][:,permutation]*sign)))
        loss_delta=float(cf['negative_twice_elbo']-c['negative_twice_elbo'])
        prediction_error=float(np.max(abs(c['conditional_residual_hz']-cf['conditional_residual_hz'])))
        state=p.state(x)
        decoded=np.concatenate([scan.hardware(scan.tracks[i],state['beta']) for i in p.members])
        feature_hardware=c['features'][:,:nb]@c['coefficient'][:nb]
        beta_error=float(np.max(abs(decoded-feature_hardware)))
        # State smooth uses 11.5-GHz Hz, physical model multiplies by q.
        ns=p.smooth.shape[1]
        decoded_smooth=np.concatenate([scan.tracks[i]['rf_hz']/11.5e9*scan.rx_basis[i]@state['smooth'][scan.tracks[i]['receiver']-1] for i in p.members])
        smooth_error=float(np.max(abs(decoded_smooth-c['features'][:,nb:nb+ns]@c['coefficient'][nb:nb+ns])))
        zero=[int(k) for k in range(nb) if not np.any(c['features'][:,k])]
        assert design_error < 1e-10 and abs(loss_delta) < 2e-5 and prediction_error < 2e-5
        assert beta_error < 1e-7 and smooth_error < 1e-7
        # Four arbitrary positions test objective equality away from the saved optimum.
        grid=[]
        for point in ([0.,0.],[-3.,2.],[2.,-3.],[8.,8.]):
            delta=float(pf.calculate(np.asarray(point))['negative_twice_elbo']-p.calculate(np.asarray(point))['negative_twice_elbo'])
            assert abs(delta)<2e-5
            grid.append(dict(x=point,loss_difference=delta))
        result['arms'][arm]=dict(saved_objective_replay_difference=float(c['negative_twice_elbo']-record['negative_twice_elbo']),
            label_flip_design_error=design_error,label_flip_loss_difference=loss_delta,
            label_flip_prediction_max_difference_hz=prediction_error,state_beta_reconstruction_max_difference_hz=beta_error,
            state_smooth_reconstruction_max_difference_hz=smooth_error,unused_hardware_columns=zero,
            position_invariance_checks=grid,curved_points=int(keep.sum()),predictive_points=sum(e['points'] for e in entries),
            supported_orbit_families=len(p.supported))
    return result


def input_inventory():
    result=[];all_rf={}
    for low in sorted((ROOT/'ch1_4').glob('DS24-*/observations.json')):
        case=low.parent.name;high=ROOT/'ch5_8'/case/'observations.json'
        if not high.exists():continue
        rows={s:read(ROOT/s/case/'observations.json') for s in ('ch1_4','ch5_8')}
        tracking=read(low.parent/'tracking.json');source=tracking['source'];anchor=tracking['clock_anchor']
        receivers=sorted({p['receiver_id'] for p in source['probes']})
        lookup={}
        for probe in source['probes']:
            eligible=[c for c in probe['candidates'] if c['passed_fractional_margin_gate'] is True]
            if not eligible:continue
            candidate=max(eligible,key=lambda c:(c['fractional_margin'],-c['candidate_rank']))
            identity=f"{source['session_id']}:{probe['receiver_id']}:{probe['valid_start_counter']}"
            oid='sha256:'+hashlib.sha256(identity.encode()).hexdigest()
            lookup[oid]=(probe,candidate)
        arms={}
        for sub,observations in rows.items():
            allowed=range(1,5) if sub=='ch1_4' else range(5,9)
            assert {r['observation_id'] for r in observations}=={oid for oid,(p,c) in lookup.items() if p['channel'] in allowed}
            for row in observations:
                probe,candidate=lookup[row['observation_id']]
                assert row['receiver']==receivers.index(probe['receiver_id'])+1
                assert row['channel']==probe['channel'] and row['actual_rf_hz']==probe['actual_rf_hz']
                assert row['measured_cfo_hz']==candidate['fractional_tracking_cfo_hz']
                t=(probe['valid_start_counter']-anchor['sample_counter'])/source['sample_rate_hz']+source['probe_ms']*.0005
                assert abs(row['time_s']-t)<1e-10
                all_rf.setdefault(row['channel'],set()).add(row['actual_rf_hz'])
            obs={r['observation_id']:r for r in observations}
            tracks=read(ROOT/sub/case/'tracks.json');max_error=0.;points=0
            for track in tracks:
                for oid,t,v in zip(track['observation_ids'],track['times'],track['values'],strict=True):
                    row=obs[oid];delta=(v-row['measured_cfo_hz'])/PERIOD
                    max_error=max(max_error,abs(delta-round(delta)))
                    assert abs(delta-round(delta))<1e-9
                    assert track['rf_hz']==row['actual_rf_hz'] and track['channel']==row['channel'] and t==row['time_s']
                    points+=1
            prepared=read(ROOT/sub/case/'prepared.json')
            assert prepared['metadata']['channel_filter_before_graph_and_calibration']
            arms[sub]=dict(observations=len(observations),graph_points=points,tracks=len(tracks),
                graph_alias_max_noninteger_error=max_error,radio_noise=read(ROOT/sub/case/'radio_noise.json')['constant_radio_sigma_hz'])
        lowbank=np.load(ROOT/'ch1_4'/case/'bank.npz');highbank=np.load(ROOT/'ch5_8'/case/'bank.npz')
        same_bank=all(np.array_equal(lowbank[k],highbank[k]) for k in lowbank.files)
        common_norads,lowj,highj=np.intersect1d(lowbank['norad'],highbank['norad'],return_indices=True)
        common_times,lowt,hight=np.intersect1d(lowbank['time_s'],highbank['time_s'],return_indices=True)
        common_states_equal=all(np.array_equal(lowbank[k][lowj][:,lowt],highbank[k][highj][:,hight]) for k in ('position_km','velocity_km_s'))
        assert common_states_equal
        same_prior=read(ROOT/'ch1_4'/'causal_phase_history'/f'{case}_forecast.json')==read(ROOT/'ch5_8'/'causal_phase_history'/f'{case}_forecast.json')
        result.append(dict(case=case,arms=arms,numerically_identical_orbit_banks=same_bank,identical_forecast_document=same_prior,
            identical_common_candidate_states=common_states_equal,
            low_bank_candidates=len(lowbank['norad']),high_bank_candidates=len(highbank['norad']),
            low_time_knots=len(lowbank['time_s']),high_time_knots=len(highbank['time_s']),
            high_only_norads=np.setdiff1d(highbank['norad'],lowbank['norad']).tolist(),
            low_only_norads=np.setdiff1d(lowbank['norad'],highbank['norad']).tolist(),
            low_max_graph_time_s=max(t['end_s'] for t in read(ROOT/'ch1_4'/case/'tracks.json')),
            high_max_graph_time_s=max(t['end_s'] for t in read(ROOT/'ch5_8'/case/'tracks.json'))))
    return dict(cases=result,rf_by_channel_hz={str(k):sorted(v) for k,v in sorted(all_rf.items())})


if __name__=='__main__':
    began=time.monotonic()
    inventory=input_inventory()
    checks=[replay(sub,case) for sub in ('ch1_4','ch5_8') for case in ('DS24-0010','DS24-0015','DS24-0019')]
    output=dict(all_assertions_passed=True,seconds=time.monotonic()-began,inventory=inventory,replays=checks,
        no_refit=True,no_context_call=True,no_RF_collection=True,no_truth_input=True)
    (OUT/'pipeline_invariants.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(dict(all_assertions_passed=True,seconds=output['seconds'],inventory_cases=len(inventory['cases']),replayed_problems=sum(len(r['arms']) for r in checks)),indent=2))
