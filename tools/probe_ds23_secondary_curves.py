"""Recover radio-only curves from unused public GLRT peaks; test new evidence."""

import argparse
import copy
import hashlib
import time
from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from diagnose_ds23_position_information import derivative_at,marginal_information
from evaluate_ds22_merged_tracks import CONFIG
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from evaluate_ds23_phase_refreshed import extend_associations
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo01_0217_improvements import candidate_profile,polynomial_proposals
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED,refit,make_problem
from probe_ds23_statistical_curvature import active_ids,replay
from propagate_ds23_arc_positions import install_tracks
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan
from run_dsx01_clean_region import zero_state
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.analysis.glrt_frequency_input import frequency_evidence
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency,prepare_phase_geometry
from leo.analysis.research.public_tracking_points import public_tracking_points
from leo.analysis.research.retained_track_likelihood import PERIOD,projected_receiver_basis
from leo.analysis.research.visible_arc_variants import deduplicate

OUT=ROOT/'reports/2026_10_19_ds23_secondary_curves'


def probe_authority(document):
    """Use the same public time/identity adapter as the frozen winning inputs."""
    if 'clock_anchor' in document and 'source' in document:
        evidence,_,_=frequency_evidence(document)
        source=document['source'];rows={}
        for i,probe in enumerate(source['probes']):
            if any(c['passed_fractional_margin_gate'] for c in probe['candidates']):
                rows[i]=dict(observation_id='sha256:'+hashlib.sha256(evidence.ids[i].encode()).hexdigest(),time_s=float(evidence.time_s[i]))
        return source,rows
    observations,_=public_tracking_points(document)
    by_support={(o['native_receiver_id'],o['valid_start_counter']):o for o in observations}
    fs=document['sample_rate_hz'];rows={}
    for i,probe in enumerate(document['probes']):
        start=probe['valid_start_counter']+round(probe['probe_start_ms']*fs/1000)
        if (probe['receiver_id'],start) in by_support:rows[i]=by_support[probe['receiver_id'],start]
    return document,rows


def peak_noise(metadata,margin):
    if not np.isfinite(margin) or margin<=0:raise ValueError('positive finite GLRT margin required')
    if metadata['extra_parameter_BIC_gain']<=0:return float(metadata['constant_radio_sigma_hz'])
    return float(np.sqrt(np.clip(metadata['floor_sigma_hz']**2+metadata['strength_hz2']/margin,40**2,600**2)))


def information(p,x,powers):
    c=p.calculate(x);d=derivative_at(p,x,c['coefficient'],.01)[p.keep]
    weight=powers[p.noise_groups[p.keep]]*c['noise_precision'][p.noise_groups[p.keep]]/p.point_noise[p.keep]**2
    return marginal_information(d,c['features'][p.keep],weight,c['coefficient_prior_precision'])


def run(case):
    started=time.monotonic();scan0=final_scan(case);original=read(SOURCE/case/'result.json');node0=original['final_node']
    learned=read(LEARNED/(case+'.json'));primary=learned['results']['mean_and_distribution'];keep0=np.array(primary['mask'],bool)
    model=learned['hyperparameters_from_pre_RF_TLE_only'];base=problem(scan0,node0,'c0',keep0)
    powers0=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    _,receipts=phase_widths(scan0,base.labels);means=forecast_phase_mean(receipts,model['shrinkage'])
    p,x=replay(scan0,node0,keep0,'c0',powers0,means,model,primary['arms']['c0'])
    extension=extend_associations(p,x,primary['arms']['c0']['gates'])
    # Exclude all original calibration slots, even inactive slots, and every
    # already-associated output track. A secondary peak retains its probe ID.
    excluded_keys={r['component'] for r in extension['tracks']}|{r['component'] for r in base.rows}
    excluded={oid for t in scan0.tracks if t['key'] in excluded_keys for oid in t['observation_ids']}
    document=read(SOURCE/case/'tracking.json');source,probe_rows=probe_authority(document)
    assert {o['observation_id'] for o in probe_rows.values()}=={o['observation_id'] for o in read(SOURCE/case/'observations.json')}
    receivers=sorted({v['receiver_id'] for v in source['probes']});lanes={}
    for pi,probe in enumerate(source['probes']):
        obs=probe_rows.get(pi)
        if obs is None or obs['observation_id'] in excluded:continue
        eligible=[c for c in probe['candidates'] if c['passed_fractional_margin_gate']]
        winner=max(eligible,key=lambda c:(c['fractional_margin'],-c['candidate_rank']))
        lane=(receivers.index(probe['receiver_id'])+1,probe['channel'],probe['actual_rf_hz'])
        for c in eligible:
            lanes.setdefault(lane,[]).append(dict(time_s=obs['time_s'],probe=pi,
                cfo_hz=c['fractional_tracking_cfo_hz'],margin=c['fractional_margin'],rank=c['candidate_rank'],
                winner=c is winner,observation_id=obs['observation_id']))
    cfg=TrackConfig(**read(CONFIG)['config']);proposals=[];lane_receipts=[]
    for number,(lane,candidates) in enumerate(sorted(lanes.items())):
        reps,_=deduplicate([c['cfo_hz'] for c in candidates],[c['margin'] for c in candidates],[c['probe'] for c in candidates])
        candidates=sorted([candidates[i] for i in reps],key=lambda c:(c['time_s'],c['cfo_hz']))
        models=polynomial_proposals(candidates,cfg,trials=1800,seed=20261019+int(case.split('-')[1])*16+number)
        reserved=set();accepted=[]
        for m in models:
            ids={candidates[i]['probe'] for i in m['indices']}
            if reserved&ids:continue
            reserved|=ids;accepted.append(m)
            proposals.append(dict(lane=lane,candidates=[candidates[i] for i in m['indices']],model=m))
        lane_receipts.append(dict(lane=lane,peaks=len(candidates),probes=len({c['probe'] for c in candidates}),
                                  radio_models=len(models),exclusive_proposals=len(accepted)))
        print(case,'radio lane',lane[:2],'models',len(accepted),flush=True)
    proposals.sort(key=lambda r:-r['model']['gain']);OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/(case+'_proposals.json'),dict(case=case,proposals=proposals,lanes=lane_receipts,
        source_sha256=sha(Path(__file__)),tracking_sha256=sha(SOURCE/case/'tracking.json'),
        excluded_observation_ids=sorted(excluded),GPS_or_orbits_used_for_curve_discovery=False,
        trials_per_lane=1800,max_joint_additions_tested=4,seed_rule='20261019 + numeric scan * 16 + lane index'))
    state=p.state(x);widths,all_receipts=phase_widths(scan0,list(range(len(scan0.norads))))
    all_means=forecast_phase_mean(all_receipts,model['shrinkage']);widths=np.array(widths)*model['multiplier']
    original_ids=active_ids(scan0,node0,keep0);noise=read(SOURCE/case/'radio_noise.json')
    trials=[];accepted=[];final_pair=primary['arms'];current=(scan0,node0,keep0,powers0)

    def augmented(context,track,j,alias):
        scan,node,keep,powers=context;trial_scan=copy.copy(scan);trial_scan.fixed_window_noise=copy.deepcopy(scan.fixed_window_noise)
        for c in track['source_peaks']:
            trial_scan.fixed_window_noise['per_observation_noise_sigma_hz'][c['observation_id']]=peak_noise(noise,c['margin'])
        trial_node=copy.deepcopy(node);trial_node['seed']['rows'].append(dict(component=track['key'],candidate_index=j,
            candidate_norad=int(scan.norads[j]),active_curvature=True));trial_node['seed']['state']=zero_state(scan)
        trial_node['aliases'].append(alias);install_tracks(trial_scan,scan.tracks+[track],trial_node['seed']['rows'])
        trial_keep=np.r_[keep,np.ones(len(track['times']),bool)]
        # Preserve the frozen old powers. Replication votes use active owners.
        old=[powers[k] for k,(r,sl) in enumerate(zip(base.rows,base.slices,strict=True)) if r['candidate_index']==j and keep0[sl].any()]
        power=min(old) if old else .2
        return trial_scan,trial_node,trial_keep,np.r_[powers,power]

    def fit_context(context):
        scan,node,keep,powers=context;probe=problem(scan,node,'c0',keep);_,r=phase_widths(scan,probe.labels)
        mu=forecast_phase_mean(r,model['shrinkage'])
        arms={arm:refit(scan,node,keep,arm,powers,mu,model['multiplier'],model['nu']) for arm in ('c0','fitted_c')}
        failures=sorted({r['component'] for arm in arms for r in arms[arm]['gates']['tracks'] if not r['compatible']})
        local,xlocal=replay(scan,node,keep,'c0',powers,mu,model,arms['c0'])
        return dict(arms=arms,paired_valid=not failures,failures=failures,local_information=information(local,xlocal,powers))

    for number,proposal in enumerate(proposals[:4]):
        rx,ch,rf=proposal['lane'];peaks=proposal['candidates'];times=np.array([c['time_s'] for c in peaks]);values=np.array(proposal['model']['values'])
        dummy=dict(receiver=rx,channel=ch,times=times,rf_hz=rf)
        radio=scan0.hardware(dummy,state['beta'])+rf/11.5e9*projected_receiver_basis(times)@state['smooth'][rx-1]
        f,e,d=phase_linear_frequency(prepare_phase_geometry(scan0.sky,times),*latlon(x),rf_hz=rf)
        screen=candidate_profile(values-radio,f+d*all_means[:,None],d,e,scan0.radio_sigma_hz,widths)
        ordered=[int(j) for j in np.argsort(screen['cost']) if np.isfinite(screen['cost'][j])][:3]
        track=dict(key=f'{case}-SECONDARY-{number:03}',receiver=rx,channel=ch,rf_hz=rf,bank='CH1-4' if ch<=4 else 'CH5-8',
            times=times,values=values,observation_ids=[c['observation_id'] for c in peaks],pieces=[],
            start_s=float(times.min()),end_s=float(times.max()),quality_status='no_structure_detected',source_peaks=peaks)
        lift=(values-np.array([c['cfo_hz'] for c in peaks]))/PERIOD
        assert np.allclose(lift,np.rint(lift),atol=1e-8)
        assert not (set(track['observation_ids'])&excluded)
        candidates=[]
        for j in ordered:
            context=augmented((scan0,node0,keep0,powers0),track,j,int(screen['aliases'][j]))
            result=fit_context(context);result.update(candidate_index=j,norad=int(scan0.norads[j]),alias=int(screen['aliases'][j]))
            candidates.append(result)
        valid=[r for r in candidates if r['paired_valid']]
        chosen=min(valid,key=lambda r:r['arms']['c0']['negative_twice_elbo']) if valid else None
        joint=None
        if chosen is not None:
            context=augmented(current,track,chosen['candidate_index'],chosen['alias'])
            joint=fit_context(context)
            if joint['paired_valid']:
                assert original_ids<=active_ids(context[0],context[1],context[2])
                current=context;final_pair=joint['arms'];accepted.append(dict(proposal=number,norad=chosen['norad'],track=track))
        trials.append(dict(proposal=number,track=track,candidates=candidates,chosen=chosen,joint=joint))
        print(case,'new curve',number,'independent valid',chosen is not None,'joint valid',joint is not None and joint['paired_valid'],flush=True)
    write(OUT/(case+'.json'),dict(case=case,baseline=primary['arms'],baseline_information=information(p,x,powers0),
        proposals_total=len(proposals),trials=trials,accepted=accepted,arms=final_pair,
        original_active_ids=sorted(original_ids),final_active_ids=sorted(active_ids(current[0],current[1],current[2])),
        source_sha256=sha(Path(__file__)),proposal_input_sha256=sha(OUT/(case+'_proposals.json')),
        prior_input_sha256=sha(LEARNED/(case+'.json')),GPS_used=False,seconds=time.monotonic()-started,
        retained_original_points=True,new_noise_comes_from_each_selected_peak_margin=True,
        same_c_pair_observations_labels_aliases_and_budget=True,
        local_information_is_conditioned_not_calibrated_accuracy=True,
        no_exhaustiveness_claim=True))
    print(case,'done accepted',len(accepted),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
