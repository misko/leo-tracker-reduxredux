"""One shared-family extension seeded by already RF-qualified curved evidence."""

import copy
from pathlib import Path

import numpy as np

from probe_ds23_family_cavity_position import fit_configuration
from probe_ds23_reentry_family_cavity import audit_baseline
from run_algo01_ds23_sample import read, write, sha
import run_ds23_dbg01_iteration_002 as iteration
from probe_ds23_dbg01_iteration002_extra_curves import OUT as EXTRA

OUT = iteration.RAW/'family_seeded_growth'


def extension_offers(accepted, nominations):
    by_key = {a['component']: a for trial in accepted for a in trial['additions']}
    families = {a['norad'] for a in by_key.values()}
    for row in nominations['targets']:
        best = row['best']
        if best is not None and best['norad'] in families:
            component = row['target']['component']
            by_key.setdefault(component, dict(component=component, candidate_index=best['candidate_index'],
                norad=best['norad'], alias=int(best['aliases'][0])))
    return sorted(by_key.values(), key=lambda r:r['component'])


def one(case):
    d = iteration.current_setup(case)
    original_root = iteration.RAW/'single_curve_reentry'
    initial, extra = [read(p/(case+'_positions.json')) for p in [original_root, EXTRA]]
    if not read(EXTRA/(case+'_audit.json'))['all_passed']:
        raise ValueError('audit additional curves before shared-family extension')
    accepted = [r['selected'] for r in [initial, extra] if r['selected'] is not None]
    additions = extension_offers(accepted, read(original_root/(case+'_nominations.json')))
    trials = list(accepted)
    extension = None
    if accepted and len(additions) > max(len(r['additions']) for r in accepted):
        node, keep = copy.deepcopy(d['node']), d['keep'].copy()
        for row in additions:
            k = next(k for k, r in enumerate(node['seed']['rows']) if r['component'] == row['component'])
            node['seed']['rows'][k].update(candidate_index=row['candidate_index'], candidate_norad=row['norad'])
            node['aliases'][k] = row['alias']
            keep[d['base'].slices[k]] = True
        labels = sorted({r['candidate_index'] for r in node['seed']['rows']})
        extension = fit_configuration(dict(d, keep=keep), node, d['entries'], d['all_means'][labels])
        extension.update(mask=keep, additions=additions, added_curved_points=int(keep.sum()-d['keep'].sum()))
        trials.append(extension)
        print(case, 'family-seeded extension', extension['added_curved_points'], extension['paired_valid'], flush=True)
    checks = []
    for trial in trials:
        dd = dict(d, node=trial['node'], keep=np.asarray(trial['mask'], bool),
                  entries=trial['entries'], means=np.asarray(trial['means']))
        for arm, saved in trial['arms'].items():
            checks.append(audit_baseline(dd, arm, saved))
    passing = [t for t in trials if t['paired_valid']]
    passing.sort(key=lambda r:(-r['added_curved_points'], tuple(a['component'] for a in r['additions']),
                              r['arms']['c0']['corrected_selection_loss']))
    selected = passing[0] if passing else None
    coverage = read(iteration.RAW/case/'inventory.json')['arms']
    if selected:
        dd = dict(d, node=selected['node'], keep=np.asarray(selected['mask'], bool), entries=selected['entries'],
                  means=np.asarray(selected['means']), arms=selected['arms'])
        coverage = {arm:iteration.baseline.inventory(dd, arm) for arm in ['c0', 'fitted_c']}
    result = dict(case=case, trials=trials, extension=extension, selected=selected, coverage=coverage,
        all_passed=True, checks=checks, selection_before_new_geographic_evaluation=True,
        original_points_and_gates_preserved=True, no_new_ALGO_release=True,
        input_position_sha256={str(p):sha(p/(case+'_positions.json')) for p in [original_root, EXTRA]})
    write(OUT/(case+'.json'), result)
    return dict(case=case, all_passed=True, endpoint_arms_audited=len(checks),
                extension_paired_valid=extension['paired_valid'] if extension else None,
                selected_added_points=selected['added_curved_points'] if selected else 0)


def main():
    iteration.configure()
    OUT.mkdir(exist_ok=True)
    path = OUT/'protocol.json'
    if path.exists():
        raise FileExistsError('preserve sealed family extension')
    write(path, dict(cases=read(iteration.RAW/'protocol.json')['cases'],
        algorithm='existing ALGO02/03 shared-family extension after covariance-aware reentry',
        rule='union approved additions and original leading curve nominees sharing their satellite ID',
        at_most_one_new_cold_union_fit_per_case=True,
        final_selection='maximum added points among original paired-gate-valid trials',
        no_GPS_future_TLE_new_priors_or_gate_relaxation=True,
        one_correction_per_satellite=True, matched_c0_fitted_c=True,
        regional_start=[0,0], phase_rounds=5, position_steps_per_round=48,
        source_sha256=sha(Path(__file__))))
    rows = [one(c) for c in read(iteration.RAW/'protocol.json')['cases']]
    write(OUT/'execution.json', dict(rows=rows, all_passed=True, all_terminal=True,
        sealed_before_new_geographic_evaluation=True))


if __name__ == '__main__':
    main()
