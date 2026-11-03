"""Complete scans whose receiver split left unrepresented predictive labels.

The initial driver and completed results remain immutable. Only hypotheses
outside the existing model's domain are rejected; no observation is removed.
Representable partial trials are replayed and reused before fitting new ones.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time
import numpy as np

from algo02_scan import pair_passes
from calibrate_ds23_excluded_catalogue import OUT, ARMS, context
from ds23_excluded_catalogue import apply_changes
from ds23_receiver_family_search import orphan_predictive_labels
from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_symmetric_family_code import family_code, observed_labels, symmetric_gain
from fit_ds23_excluded_catalogue import prepare as initial_protocol, hypotheses
from probe_ds23_frequency_events import refit
from probe_ds23_symmetric_family_selection import constrain
from run_algo01_ds23_sample import ROOT, read, write, sha
from run_dsx01_clean_region import zero_state


def prepare():
    base = initial_protocol()
    path = OUT/'fit_protocol_v2.json'
    hashes = {str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),
        ROOT/'tools/fit_ds23_excluded_catalogue.py', ROOT/'tools/ds23_receiver_family_search.py')}
    if path.exists():
        p = read(path)
        if p['source_sha256']!=hashes:
            raise ValueError('frozen support-completion amendment changed')
        return p
    p = dict(base, source_sha256=hashes, initial_fit_protocol_sha256=sha(OUT/'fit_protocol.json'),
        amendment='reject only nomination hypotheses with predictive labels absent from the curved model; preserve all observations and remaining hypotheses',
        preserve_all_completed_initial_results=True,
        partial_trials_reused_only_after_node_alias_entry_code_and_RF_endpoint_replay=True,
        initial_driver_unchanged=True, hypothesis_slots_not_refilled_after_domain_rejection=True,
        declared_before_geographic_evaluation=not(OUT/'evaluation.json').exists())
    if not p['declared_before_geographic_evaluation']:
        raise ValueError('support amendment must precede geographic evaluation')
    write(path,p)
    return p


def run(case):
    protocol = prepare()
    directory = OUT/case
    path = directory/'result.json'
    if path.exists():
        return dict(case=case,cached=True,result_sha256=sha(path))
    began = time.monotonic()
    scan,node,keep,base,old,signed,model,powers,means,entries,calibration = context(case)
    screen_path = OUT/(case+'_screen.json')
    screen = read(screen_path)
    if not screen['qualified'] or screen['calibration_sha256']!=sha(OUT/(case+'_calibration.json')):
        raise ValueError('completion requires a qualified, unchanged catalogue screen')
    full_means = np.asarray(screen['means_s'])
    incumbent = signed['policy_arms']
    r = calibration['arms']['c0']
    p = make_event_problem(scan,node,np.asarray(calibration['mask'],bool),'c0',np.asarray(r['phase_reference']),powers,means,model,[])
    attach_event_predictive(p,calibration['predictive_entries'],powers)
    position = np.asarray(r['endpoint_east_north_km'])
    if abs(p.calculate(position)['negative_twice_elbo']-r['negative_twice_elbo'])>1e-3:
        raise ValueError('calibration changed before completion')
    offers = hypotheses(scan,node,p,position,entries,screen)
    saved_plan = read(directory/'hypotheses.json')
    if saved_plan['screen_sha256']!=sha(screen_path):
        raise ValueError('initial hypothesis plan source changed')
    incumbent_code = family_code(len(scan.norads),observed_labels(node,entries,keep,base.slices))
    trials,rejected,reused = [],[],[]
    for k,offered in enumerate([dict(choices=[],gain=0.,changed_family_count=0)]+offers):
        changed,predictive = apply_changes(node,entries,offered['choices'])
        changed['seed']['state'] = zero_state(scan)
        missing = orphan_predictive_labels(changed,predictive)
        if missing:
            rejection = dict(index=k,choices=offered['choices'],unsupported_predictive_indices=missing,
                reason='existing curved-supported predictive model cannot represent these labels',
                no_observations_removed=True)
            rejected.append(rejection)
            write(directory/f'rejected_{k:02d}.json',rejection)
            continue
        labels = sorted({r['candidate_index'] for r in changed['seed']['rows']})
        code = family_code(len(scan.norads),observed_labels(changed,predictive,keep,base.slices))
        cached_path = directory/f'trial_{k:02d}.json'
        if cached_path.exists():
            trial = read(cached_path)
            if (trial['node']['seed']['rows']!=changed['seed']['rows'] or trial['node']['aliases']!=changed['aliases'] or
                    trial['predictive_entries']!=predictive or abs(trial['code']-code)>1e-10):
                raise ValueError('partial trial differs from the original hypothesis')
            for arm in ARMS:
                saved = trial['arms'][arm]
                q = make_event_problem(scan,changed,keep,arm,np.asarray(saved['phase_reference']),powers,full_means[labels],model,[])
                attach_event_predictive(q,predictive,powers)
                if abs(q.calculate(np.asarray(saved['endpoint_east_north_km']))['negative_twice_elbo']-saved['negative_twice_elbo'])>1e-3:
                    raise ValueError('partial RF endpoint does not replay')
            reused.append(dict(path=str(cached_path.relative_to(ROOT)),sha256=sha(cached_path)))
        else:
            arms = {a:refit(scan,changed,keep,a,powers,full_means[labels],model,[],predictive) for a in ARMS}
            gains = {a:symmetric_gain(incumbent[a]['negative_twice_elbo'],incumbent_code,arms[a]['negative_twice_elbo'],code) for a in ARMS}
            trial = dict(index=k,choices=offered['choices'],changed_family_count=offered['changed_family_count'],
                node=changed,predictive_entries=predictive,arms=arms,code=code,coded_gains=gains,
                paired_valid=pair_passes(arms,include_linear=True))
            write(cached_path,trial)
        trials.append(trial)
    finalists = sorted([t for t in trials if not t['paired_valid'] and t['coded_gains']['c0']>2*np.log(7)],
        key=lambda t:t['arms']['c0']['negative_twice_elbo']+t['code'])[:2]
    for trial in finalists:
        arms = constrain(scan,trial['node'],keep,powers,full_means,model,trial['predictive_entries'],trial['arms'])
        gains = {a:symmetric_gain(incumbent[a]['negative_twice_elbo'],incumbent_code,arms[a]['negative_twice_elbo'],trial['code']) for a in ARMS}
        refined = dict(trial,stage='constrained',arms=arms,coded_gains=gains,paired_valid=pair_passes(arms,include_linear=True))
        trials.append(refined)
        write(directory/f"trial_{trial['index']:02d}_constrained.json",refined)
    valid = [t for t in trials if t['paired_valid'] and all(g>2*np.log(7) for g in t['coded_gains'].values())]
    best = min(valid,key=lambda t:t['arms']['c0']['negative_twice_elbo']+t['code']) if valid else None
    write(path,dict(case=case,accepted=best is not None,selected_index=best['index'] if best else None,
        selected_stage=best.get('stage','cold') if best else None,selected_node=best['node'] if best else node,
        selected_entries=best['predictive_entries'] if best else entries,selected_choices=best['choices'] if best else [],
        policy_arms=best['arms'] if best else incumbent,incumbent_arms=incumbent,
        trial_count=len(trials),code=best['code'] if best else incumbent_code,
        coded_gains=best['coded_gains'] if best else {},original_mask=keep,means_s=full_means,
        powers=powers,incumbent_code=incumbent_code,screen_sha256=sha(screen_path),
        calibration_sha256=sha(OUT/(case+'_calibration.json')),seconds=time.monotonic()-began,
        no_original_points_removed=True,no_GPS_or_future_TLE_used=True,
        source_sha256=protocol['source_sha256'],rejected_hypotheses=rejected,reused_partial_trials=reused))
    receipt = dict(case=case,accepted=best is not None,rejected_hypotheses=len(rejected),
        reused_partial_trials=len(reused),seconds=time.monotonic()-began)
    print(receipt,flush=True)
    return receipt


if __name__=='__main__':
    prepare()
    cases = read(OUT/'unsupported_hypothesis_amendment_plan.json')['affected_cases']
    receipts=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(run,c):c for c in cases}
        for f in as_completed(futures):
            try:receipts.append(f.result())
            except Exception as exc:receipts.append(dict(case=futures[f],error=repr(exc)))
    write(OUT/'support_completion_execution.json',dict(all_terminal=True,receipts=receipts,
        errors=[r for r in receipts if 'error'in r]))
    print('Terminal',len(receipts),'errors',sum('error'in r for r in receipts),flush=True)
