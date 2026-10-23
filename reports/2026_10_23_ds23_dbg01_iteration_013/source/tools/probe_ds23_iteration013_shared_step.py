"""Existing shared receiver/band events at an independently supported RF split."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import signal
import numpy as np

import run_ds23_dbg01_iteration_013 as runner
import probe_ds23_frequency_events as events
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'shared_step'
KINDS=('band','receiver')


def contexts(trials,target,lookup):
    tau=target['time_s'];result=[]
    for trial in trials:
        if not 1<=len(trial['additions'])<=2 or target['component'] not in {a['component'] for a in trial['additions']}:continue
        tracks=[lookup[a['component']] for a in trial['additions']]
        if not all(t['receiver']==target['receiver'] and (t['channel']>4)==(target['channel']>4)
            and sum(t['times']<tau)>=4 and sum(t['times']>=tau)>=4 for t in tracks):continue
        result.append(trial)
    return sorted(result,key=lambda t:(-t['added_curved_points'],tuple(a['component'] for a in t['additions'])))[:2]


def choose(trials):
    passing=[t for t in trials if t['accepted']]
    if not passing:return None
    # More data is considered only after each variant beats its identical-mask
    # null in both arms. Compare raw bounds only within an identical scope.
    maximum=max(t['added_curved_points'] for t in passing)
    return min((t for t in passing if t['added_curved_points']==maximum),key=lambda t:(t['arms']['c0']['negative_twice_elbo'],t['kind']))


def one(case):
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('480s shared-step cap')));signal.alarm(480)
    runner.configure();d=runner.engine.current_setup(case);targets=read(runner.RAW/'step_transfer_diagnostic'/(case+'.json'))['targets'];trials=[]
    original=read(runner.RAW/case/'inventory.json')['arms'];lookup={t['key']:t for t in d['scan'].tracks}
    candidates=read(runner.RAW/'single_curve_reentry'/(case+'_positions.json'))['trials']
    for target in targets[:1]:
        supporting=[r for r in target['independent_original_parent_curves'] if r['channel']!=target['channel'] and
            (r['channel']>4)==(target['channel']>4) and r['gain']>0 and r['amplitude_hz']*target['mean_difference_hz']<0]
        if not supporting:continue
        penalty=float(2*np.log(max(1,len(target['times'])-7)*len(KINDS)))
        for null in contexts(candidates,target,lookup):
            for kind in KINDS:
                event=dict(kind=kind,receiver=target['receiver'],time_s=target['time_s'],sigma_hz=300.)
                if kind=='band':event['band']=int(target['channel']>4)
                pair={a:events.refit(d['scan'],null['node'],np.asarray(null['mask'],bool),a,d['powers'],np.asarray(null['means']),d['model'],[event],null['entries']) for a in ['c0','fitted_c']}
                gains={a:null['arms'][a]['negative_twice_elbo']-r['negative_twice_elbo'] for a,r in pair.items()}
                accepted=bool(valid(pair) and all(r['final_phase_change_s']<=.01 for r in pair.values()) and min(gains.values())>penalty)
                trial=dict(kind=kind,arms=pair,events=[event],gains=gains,search_penalty=penalty,paired_valid=bool(valid(pair)),
                    accepted=accepted,added_curved_points=null['added_curved_points'],additions=null['additions'],node=null['node'],mask=null['mask'],means=null['means'],entries=null['entries'],
                    null_arms=null['arms'],same_mask_null_reused_without_refit=True,supported_by_other_original_parent_family=[r['component'] for r in supporting])
                trials.append(trial);write(OUT/(case+'_checkpoint.json'),dict(trials=trials));print(case,kind,null['added_curved_points'],'paired',trial['paired_valid'],'penalized acceptance',accepted,flush=True)
    selected=choose(trials);write(OUT/(case+'.json'),dict(case=case,trials=trials,selected=selected,RF_selection_before_geographic_scoring=True))
    signal.alarm(0);return dict(case=case,trials=len(trials),selected=selected is not None)


def main():
    runner.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve shared-step experiment')
    cases=read(runner.RAW/'protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),event_driver_sha256=sha(Path(events.__file__)),
        existing_event_model_reused_not_a_new_unrestricted_per_track_correction=True,
        event_time_and_receiver_band_frozen_from_step_transfer_diagnostic=True,
        at_least_one_other_original_parent_family_on_another_same_band_channel_with_same_sign_step_required=True,
        fixed_event_prior_SD_hz=300,models=list(KINDS),maximum_scopes=2,
        scopes='existing focus single and largest wholly spanning same-band pair, at least4points each side',
        identical_mask_no_event_fits_reused_exactly=True,
        search_penalty='2log((source_points-7)*2 event kinds); proper event Gaussian complexity also in marginal bound',
        both_c_arms_must_improve_RF_bound_beyond_same_penalty_and_pass_all_original_gates=True,
        original_power_phase_physical_priors_aliases_and_cold5x48budget_unchanged=True,
        no_GPS_future_TLE_new_RF_IQ_or_postfit_point_trim=True,
        previous_frequency_event_cohort_controls_remain_required_before_any_release=True))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,cases))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=True))


if __name__=='__main__':main()
