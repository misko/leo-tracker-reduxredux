"""Cold paired fits offering complete, currently unused nominee families."""

import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

from algo02_scan import pair_passes
from debug_ds23_0041_influence import OUT, CASE, ARMS
from probe_algo03_frame_peak_recovery import context
from probe_ds23_frequency_events import parameters, refit
from investigate_ds23_0268_remaining_tracks import fine_receiver_basis
from run_algo01_ds23_sample import read, write, sha


def initialize():
    destination = OUT/'reentry_protocol.json'
    if destination.exists():
        return read(destination)
    scan, node, mask, base, old = context(CASE)
    entries = old['linear_entries'] if old['linear_paired_valid'] else []
    occupied = {e['component'] for e in entries}
    used = {r['candidate_norad'] for r,sl in zip(base.rows, base.slices, strict=True) if mask[sl].any()}
    available = {}
    for row,i,sl in zip(base.rows, base.members, base.slices, strict=True):
        t = scan.tracks[i]
        if (mask[sl].any() or row['candidate_norad'] in used or t['key'] in occupied
                or len(t['times']) < 12 or np.ptp(t['times']) < 10):
            continue
        available.setdefault(row['candidate_norad'], []).append(row['component'])
    selected = sorted(available, key=lambda n:-sum(len(t['times']) for t in scan.tracks if t['key'] in available[n]))[:2]
    groups = [[n] for n in selected] + ([selected] if len(selected) > 1 else [])
    jobs = [dict(label=basis+'_'+'_'.join(map(str, group)), basis=basis, norads=group)
            for basis in ('original', 'fine') for group in groups]
    document = dict(case=CASE, jobs=jobs, available_families=available, selected_by_unused_point_count=True,
        no_fixed_satellite_whitelist_in_selection=True, source_sha256=sha(Path(__file__)),
        no_identity_alias_or_weight_change=True, retain_every_original_point_and_predictive_entry=True,
        same_c_masks_priors_and_search_budgets=True, GPS_used=False, future_TLE_used=False,
        fine_basis_normalization_matches_average_original_prior_variance=True,
        regional_width_km=25, cold_start_km=[0,0], phase_rounds=5, position_steps=48)
    write(destination, document)
    return document


def job(request):
    destination = OUT/('reentry_'+request['label']+'.json')
    if destination.exists():
        return dict(label=request['label'], cached=True)
    scan, node, mask, base, old = context(CASE)
    powers, means, hyper = parameters(scan, base, old)
    entries = old['linear_entries'] if old['linear_paired_valid'] else []
    keep = mask.copy()
    for row,sl in zip(base.rows, base.slices, strict=True):
        if row['candidate_norad'] in request['norads']:
            keep[sl] = True
    if request['basis'] == 'fine':
        scan = copy.copy(scan)
        scan.rx_basis = [fine_receiver_basis(t['times']) for t in scan.tracks]
        node = copy.deepcopy(node)
        node['seed']['state']['smooth'] = np.zeros((2, scan.rx_basis[0].shape[1]))
    pair = {arm:refit(scan, node, keep, arm, powers, means, hyper, [], entries) for arm in ARMS}
    result = dict(case=CASE, request=request, arms=pair, paired_valid=pair_passes(pair, include_linear=True),
        mask=keep, original_mask=mask, additional_curved_points=int(keep.sum()-mask.sum()),
        GPS_used=False, future_TLE_used=False, original_points_never_removed=True)
    write(destination, result)
    receipt = dict(label=request['label'], paired_valid=result['paired_valid'], added=result['additional_curved_points'])
    print(receipt, flush=True)
    return receipt


def main():
    protocol = initialize()
    results = []
    with ProcessPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(job, r):r['label'] for r in protocol['jobs']}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(dict(label=futures[future], error=repr(exc)))
    write(OUT/'reentry_execution.json', dict(results=results, all_terminal=True))


if __name__ == '__main__':
    main()
