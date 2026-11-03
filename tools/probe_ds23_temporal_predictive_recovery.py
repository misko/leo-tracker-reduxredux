"""Bounded temporal discovery; frozen, joint predictive-only position trials."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time

import numpy as np

import run_ds23_dbg01_iteration_005 as runner
import ds23_temporal_predictive_recovery as temporal
from audit_ds23_algo01_coverage import retained_metrics
from dbg01_unassociated import ownership
from evaluate_ds23_phase_refreshed import extend_associations
from probe_ds23_frequency_events import refit
from probe_ds23_reentry_family_cavity import audit_baseline
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'temporal_predictive'
METHODS={'independent':0.,'persistent5s':5.}


def protocol():
    runner.configure();parent=runner.protocol();OUT.mkdir(parents=True,exist_ok=True)
    result=dict(cases=parent['cases'],methods=METHODS,signal_fraction=.5,maximum_gap_s=10.,
        minimum_points=8,minimum_span_s=6.,permutation_controls=19,seed=2026102205,
        permutation_lane_gate='native log likelihood ratio > maximum of19 timestamp/CFO permutations +2log20',
        permutation_is_coherence_diagnostic_not_exchangeability_validated_p_value=True,
        path_gate='same family wins in both c arms; nominal Gaussian class probability >=.99; '
            'gain>2log(2methods*lanes*activefamilies); selected marginal SD<aliasperiod/20',
        maximum_paths_per_method=24,ranking='c0 correlated Gaussian gain; no geographic score',
        discovery='all unused original winning GLRT; physical RX/channel/actualRF lanes; all incumbent active curved families',
        candidate_limitation='does not discover a satellite family absent from incumbent curved calibration',
        discovery_HMM_uses_marginal_emissions_only=True,identity_check_uses_full_shared_curved_covariance=True,
        identity_probabilities_are_post_selection_compatibility_not_calibrated_truth=True,
        position_old_and_new_predictive_points_integrated_in_one_shared_covariance_block=True,
        new_points_never_update_curved_calibration=True,per_path_constant_prior_sigma_hz=300.,
        full_paths_frozen_before_position_fit_no_residual_trimming=True,
        final_acceptance='both original paired residual/phase gates and every incumbent accepted ID retained; otherwise exact incumbent',
        final_start_km=[0,0],regional_width_km=25,phase_rounds=5,steps_per_round=48,
        matched_c_arms=True,GPS_or_following_TLE_used=False,
        source_sha256=sha(Path(__file__)),helper_sha256=sha(Path(temporal.__file__)),parent_sha256=sha(runner.RAW/'protocol.json'))
    path=OUT/'protocol.json'
    if path.exists():
        if read(path)!=result:raise ValueError('preserve frozen temporal protocol')
    else:write(path,result)
    return result


def discover(case):
    output=OUT/(case+'_discovery.json')
    if output.exists():return dict(case=case,cached=True)
    began=time.monotonic();d=runner.engine.current_setup(case)
    inventory=read(runner.RAW/case/'inventory.json')['arms']
    occupied=set().union(*(set(r['accepted_observation_ids']) for r in inventory.values()))
    occupied.update(o for i in d['scan'].curved for o in d['scan'].tracks[i]['observation_ids']
                    if any(r['component']==d['scan'].tracks[i]['key'] and d['keep'][sl].any()
                           for r,sl in zip(d['base'].rows,d['base'].slices,strict=True)))
    observations=sorted([o for o in d['observations'] if o['observation_id'] not in occupied],
        key=lambda o:(o['receiver'],o['channel'],o['actual_rf_hz'],o['time_s'],o['observation_id']))
    predictions={}
    for arm,saved in d['arms'].items():
        p=runner.engine.baseline.build(d,arm,saved['phase_reference'])
        predictions[arm]=temporal.predictions(p,np.asarray(saved['endpoint_east_north_km']),d['powers'],observations)
    lanes=sorted({(o['receiver'],o['channel'],o['actual_rf_hz']) for o in observations})
    values=np.array([o['measured_cfo_hz'] for o in observations]);families=len(predictions['c0']['active'])
    penalty=float(2*np.log(len(METHODS)*len(lanes)*families));rng=np.random.default_rng(2026102205)
    results={method:dict(lanes=[],paths=[],selected=[]) for method in METHODS}
    for lane in lanes:
        indices=np.array([i for i,o in enumerate(observations) if (o['receiver'],o['channel'],o['actual_rf_hz'])==lane])
        local=[observations[i] for i in indices];times=np.array([o['time_s'] for o in local]);y=values[indices]
        if len(indices)<8:continue
        pred={arm:{k:(v[indices] if k in ['mean','variance','native_sigma','visible','features'] else v)
                       for k,v in prediction.items()} for arm,prediction in predictions.items()}
        density=temporal.density_predictions(pred['c0'],y)
        permutations=[rng.permutation(len(y)) for _ in range(19)]
        for method,tau in METHODS.items():
            h=temporal.hmm(times,density,pred['c0']['visible'],tau)
            controls=[temporal.hmm(times,temporal.density_predictions(pred['c0'],y[order],order),
                       pred['c0']['visible'],tau)['log_ratio_vs_clutter'] for order in permutations]
            threshold=max(controls)+2*np.log(20);lane_pass=h['log_ratio_vs_clutter']>threshold
            results[method]['lanes'].append(dict(lane=lane,points=len(y),native_log_ratio=h['log_ratio_vs_clutter'],
                permutation_log_ratios=controls,threshold=threshold,passed=bool(lane_pass)))
            for state,ix in temporal.path_indices(times,h['states']):
                checks={arm:temporal.path_identity(pr,y,ix) for arm,pr in pred.items()}
                j=state-1
                passed=bool(lane_pass and all(r['best_local_index']==j and r['probabilities'][j+1]>=.99
                    and r['gain_vs_clutter']>penalty and r['maximum_marginal_SD_hz']<temporal.PERIOD/20
                    for r in checks.values()) and np.array_equal(checks['c0']['aliases'],checks['fitted_c']['aliases']))
                candidate=pred['c0']['active'][j]
                fragment=dict(receiver=lane[0],channel=lane[1],rf_hz=lane[2],
                    key=f"TEMP_{method}_{len(results[method]['paths']):03d}",
                    candidate_index=candidate,norad=int(d['scan'].norads[candidate]),times=times[ix],
                    values=y[ix]+checks['c0']['aliases']*temporal.PERIOD,
                    observation_ids=[local[i]['observation_id'] for i in ix])
                record=dict(fragment=fragment,checks=checks,passed=passed,points=len(ix),span_s=float(np.ptp(times[ix])),
                    lane_coherence_passed=bool(lane_pass),discovery_mean_probability=float(h['posterior'][ix,state].mean()))
                results[method]['paths'].append(record)
        print(case,lane,'unused',len(indices),flush=True)
    for method,r in results.items():
        eligible=sorted([p for p in r['paths'] if p['passed']],key=lambda p:-p['checks']['c0']['gain_vs_clutter'])[:24]
        r['selected']=[p['fragment'] for p in eligible]
    write(output,dict(case=case,unused_points=len(observations),active_families=families,lanes=len(lanes),
        multiplicity_penalty=penalty,methods=results,seconds=time.monotonic()-began,protocol_sha256=sha(OUT/'protocol.json')))
    return dict(case=case,status='complete',paths={m:len(r['selected']) for m,r in results.items()})


def coverage(d,arm,saved,new_gates):
    p=runner.engine.baseline.build(d,arm,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km'])
    extended=extend_associations(p,x,retained_metrics(p,x));lookup={t['key']:t for t in d['scan'].tracks}
    rows=[dict(r,observation_ids=r.get('observation_ids',lookup[r['component']]['observation_ids'])) for r in extended['tracks']]
    graph_ids=ownership(rows);added={o for r in new_gates if r['compatible'] for o in r['observation_ids']}
    if graph_ids&added:raise ValueError('new GLRT path duplicates a graph association')
    ids=graph_ids|added
    if not ids<={o['observation_id'] for o in d['observations']}:raise ValueError('nonphysical observation ID')
    return dict(associated=len(ids),total_GLRT=len(d['observations']),percent=100*len(ids)/len(d['observations']),
        associated_tracks=sum(r['compatible'] for r in rows)+len(new_gates),accepted_observation_ids=sorted(ids),
        active_curved_points=int(d['keep'].sum()),predictive_points=sum(e['points'] for e in d['entries'])+len(added),
        associations=extended,new_paths=new_gates)


def positions(case):
    output=OUT/(case+'_positions.json')
    if output.exists():return dict(case=case,cached=True)
    d=runner.engine.current_setup(case);discovery=read(OUT/(case+'_discovery.json'))
    original=read(runner.RAW/case/'inventory.json')['arms'];methods={}
    for method,proposal in discovery['methods'].items():
        fragments=proposal['selected']
        if not fragments:
            methods[method]=dict(accepted=False,reason='no predictive paths passed frozen discovery checks');continue
        scan,entries=temporal.append_fragments(d['scan'],d['entries'],fragments)
        arms={arm:refit(scan,d['node'],d['keep'],arm,d['powers'],d['means'],d['model'],[],entries)
              for arm in ['c0','fitted_c']}
        dd=dict(d,scan=scan,entries=entries)
        audits={arm:audit_baseline(dd,arm,saved) for arm,saved in arms.items()}
        cov={arm:coverage(d,arm,saved,saved['linear_gates'][len(d['entries']):]) for arm,saved in arms.items()}
        preserved={arm:set(original[arm]['accepted_observation_ids'])<=set(cov[arm]['accepted_observation_ids']) for arm in arms}
        accepted=bool(valid(arms) and all(preserved.values()))
        methods[method]=dict(accepted=accepted,paired_valid=bool(valid(arms)),incumbent_IDs_preserved=preserved,
            arms=arms,coverage=cov,audits=audits,new_paths=len(fragments),new_points=sum(len(f['times']) for f in fragments),
            changed_scan_calibration_members_equal_original=scan.curved==d['scan'].curved)
        print(case,method,'paths',len(fragments),'accepted',accepted,flush=True)
    write(output,dict(case=case,methods=methods,protocol_sha256=sha(OUT/'protocol.json')))
    return dict(case=case,status='complete',accepted={m:r['accepted'] for m,r in methods.items()})


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['discover','positions'],required=True)
    args=parser.parse_args();record=protocol();rows=[]
    with ProcessPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(discover if args.stage=='discover' else positions,case) for case in record['cases']]):
            rows.append(future.result());print(rows[-1],flush=True)
    write(OUT/(args.stage+'_execution.json'),dict(rows=rows,all_terminal=True))


if __name__=='__main__':main()
