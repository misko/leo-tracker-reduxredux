"""Matched cold-start position test of RF-qualified fixed grid corrections.

Position truth is absent from this runner. Both cohorts and the acceptance
policy are frozen before any new position fits or geographic scoring.
"""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time
import numpy as np

from algo02_scan import pair_passes
from ds23_fft_grid_origin import corrected_track_values
from ds23_frequency_events import make_event_problem, attach_event_predictive
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo03_frame_peak_recovery import context, SOURCE
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_frequency_events import refit
from probe_ds23_symmetric_family_selection import bound_incumbent, SIGNED
from probe_ds23_fft_grid_origin import OUT as RF, RESPONSE
from run_algo01_ds23_sample import ROOT, read, write, sha
from run_dsx01_clean_region import zero_state

OUT = ROOT/'reports/2026_10_20_ds23_fft_grid_position'
ARMS = ('c0', 'fitted_c')


def hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in
            (Path(__file__),ROOT/'tools/ds23_fft_grid_origin.py',
             ROOT/'tools/probe_ds23_frequency_events.py',ROOT/'tools/ds23_frequency_events.py')}


def prepare():
    OUT.mkdir(exist_ok=True); path = OUT/'protocol.json'
    if path.exists():
        p = read(path)
        if p['source_sha256'] != hashes():
            raise ValueError('frozen measurement-position experiment changed')
        if sha(RF/'evaluation.json') != p['RF_evaluation_sha256']:
            raise ValueError('RF qualification changed')
        return p
    evidence = read(SIGNED/'evaluation_audit.json')['evidence']
    qualified = read(RF/'evaluation.json')['RF_qualified_groups']
    pool = []
    for case in sorted(evidence):
        d = read(RF/(case+'.json'))
        groups = {f"{d['format']}/{d['sample_rate_hz']}/{r['edge']}" for r in d['pieces']}
        if groups.intersection(qualified):
            pool.append(case)
    selected = np.random.default_rng(2026102062).choice(pool,40,replace=False).tolist()
    p = dict(development_cases=sorted(selected[:20]),confirmation_cases=sorted(selected[20:]),
        seed=2026102062,available_pool=pool,qualified_groups=qualified,source_sha256=hashes(),
        RF_evaluation_sha256=sha(RF/'evaluation.json'),response_sha256=sha(RESPONSE),
        primary='fitted-c mean AND median improve in each disjoint cohort; report all c0 changes',
        secondary='all four c-arm mean/median metrics improve in each cohort',
        signed_incumbent='published causal signed-prior policy with its frozen fallbacks',
        labels_aliases_masks_weights_noise_priors_and_search_budgets_unchanged=True,
        native_measurement_response_only_no_graph_polynomial_refit=True,
        correction_domain_abs_native_CFO_hz=[1000,399000],
        predictive_and_curved_points_corrected_consistently=True,
        cold_start_km=[0,0],box_width_km=25,phase_rounds=5,position_iterations=48,
        workers=12,paired_c_gates_original=True,failed_pair_fallback='published signed incumbent',
        no_GPS_or_future_TLE_or_cross_scan_position_information=True,
        cohorts_disjoint_for_this_correction_not_untouched_baseline_GPS=True,
        original_contracts_and_frozen_ALGO02_unchanged=True)
    write(path,p);return p


def setup(case):
    scan,node,keep,base,old = context(case)
    signed,binding = bound_incumbent(case)
    model = old['hyperparameters_from_pre_RF_TLE_only']; powers = np.asarray(old['weights'])
    if signed['accepted']:
        means = np.asarray(signed['means_s'])
    else:
        _,rows = phase_widths(scan,base.labels)
        means = forecast_phase_mean(rows,model['shrinkage'])
    entries = old['linear_entries'] if old['linear_paired_valid'] else []
    node = copy.deepcopy(node);node['seed']['state'] = zero_state(scan)
    return scan,node,keep,base,old,signed,binding,model,powers,means,entries


def corrected_scan(scan,case,protocol):
    tracking = read(SOURCE/case/'tracking.json');source = tracking.get('source',tracking)
    edges = {}
    for probe in source['probes']:
        lane = (probe['receiver_id']+1,probe['channel'])
        if lane in edges and edges[lane] != probe['edge']:
            raise ValueError('RF lane has inconsistent pilot edge')
        edges[lane] = probe['edge']
    observations = {o['observation_id']:o for o in read(SOURCE/case/'observations.json')}
    curves = read(RESPONSE)['response_curves']
    changed = copy.copy(scan); changed.tracks = []
    ids = set();deltas = []
    for track in scan.tracks:
        values = corrected_track_values(track,observations,curves,edges,source['sample_rate_hz'],
            protocol['qualified_groups'],'fast' if 'source' in tracking else 'adaptive')
        changed.tracks.append(dict(track,values=values))
        delta = values-np.asarray(track['values'])
        for oid,d in zip(track['observation_ids'],delta,strict=True):
            if abs(d)>1e-9:
                ids.add(oid);deltas.append(d)
    changed.groups = [(changed.tracks[i]['key'],[changed.tracks[i]]) for i in changed.curved]
    return changed,dict(changed_original_points=len(ids),maximum_abs_correction_hz=float(np.max(abs(np.asarray(deltas)))) if deltas else 0.,
                        RMS_correction_hz=float(np.sqrt(np.mean(np.asarray(deltas)**2))) if deltas else 0.)


def run(case):
    protocol = prepare(); path = OUT/(case+'.json')
    if path.exists():
        return dict(case=case,cached=True)
    began = time.monotonic()
    scan,node,keep,base,old,signed,binding,model,powers,means,entries = setup(case)
    incumbent = signed['policy_arms']; replays = []
    for arm in ARMS:
        saved = incumbent[arm]
        p = make_event_problem(scan,node,keep,arm,np.asarray(saved['phase_reference']),powers,means,model,[])
        attach_event_predictive(p,entries,powers)
        difference = p.calculate(np.asarray(saved['endpoint_east_north_km']))['negative_twice_elbo']-saved['negative_twice_elbo']
        if abs(difference)>1e-3:
            raise ValueError('disabled-model replay failed')
        replays.append(dict(arm=arm,RF_difference=difference))
    changed,receipt = corrected_scan(scan,case,protocol)
    # Cold null refit controls for deterministic optimizer drift, separately
    # from the saved-endpoint replay above.
    null = {a:refit(scan,node,keep,a,powers,means,model,[],entries) for a in ARMS}
    pair = {a:refit(changed,node,keep,a,powers,means,model,[],entries) for a in ARMS}
    valid = pair_passes(pair,include_linear=True)
    write(path,dict(case=case,arms=pair,paired_valid=valid,accepted=valid,
        policy_arms=pair if valid else incumbent,incumbent_arms=incumbent,
        null_cold_refit_arms=null,null_cold_paired_valid=pair_passes(null,include_linear=True),
        null_endpoint_replay=replays,measurement_correction=receipt,original_mask=keep,
        incumbent_binding=binding,seconds=time.monotonic()-began,GPS_used=False,future_TLE_used=False,
        input_sha256={n:sha(SOURCE/case/n) for n in ('observations.json','tracks.json','tracking.json')}))
    result = dict(case=case,paired_valid=valid,seconds=time.monotonic()-began,**receipt)
    print(result,flush=True);return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser();parser.add_argument('--stage',choices=('prepare','development','confirmation'),required=True)
    args = parser.parse_args();protocol = prepare()
    if args.stage != 'prepare':
        cases = protocol[args.stage+'_cases'];receipts = []
        with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
            futures = {pool.submit(run,c):c for c in cases}
            for f in as_completed(futures):
                try:
                    receipts.append(f.result())
                except Exception as exc:
                    receipts.append(dict(case=futures[f],error=repr(exc)))
                write(OUT/(args.stage+'_progress.json'),dict(receipts=receipts,completed=len(receipts),total=len(cases)))
        write(OUT/(args.stage+'_execution.json'),dict(all_terminal=True,receipts=receipts))
        print('Terminal',len(receipts),'errors',sum('error' in r for r in receipts),flush=True)
