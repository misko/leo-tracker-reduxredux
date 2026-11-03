"""Bounded extension to the remaining whole curved graph tracks, no new gates."""

import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import sys

import run_ds23_dbg01_iteration_002 as iteration
import probe_ds23_single_curved_reentry as engine
import audit_ds23_worst_iteration as auditor
from run_algo01_ds23_sample import read, write, sha

OUT = iteration.RAW/'remaining_curves'
ORIGINAL_NOMINATE = engine.nominate


def remaining_targets(ranking):
    eligible = [r for r in ranking if r['curved'] and r['points'] >= 12]
    original = {r['component'] for r in eligible[:3]}
    return [r for r in eligible if r['component'] not in original and r['points'] == r['original_points']][:3]


def nominate(data, inventory):
    targets = remaining_targets(inventory['ranking'])
    result = ORIGINAL_NOMINATE(data, dict(inventory, ranking=targets))
    result['remaining_whole_curves_after_original_three'] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['nominations', 'positions', 'audit'], required=True)
    args = parser.parse_args()
    iteration.configure()
    engine.OUT, engine.nominate, auditor.REENTRY = OUT, nominate, OUT
    OUT.mkdir(exist_ok=True)
    path = OUT/'extension_protocol.json'
    protocol = dict(cases=read(iteration.RAW/'protocol.json')['cases'],
        selection='remaining wholly unused active-curvature graph components after first three; at most three',
        original_threshold_points=12, full_causal_catalogue=True, no_new_hyperparameters_or_gates=True,
        final_all_nonempty_best_offer_combinations_and_original_nominee_controls=True,
        original_curved_predictive_masks_and_calibration_preserved=True,
        same_c0_fitted_c_points_candidates_priors_and_budgets=True,
        no_GPS_or_following_TLE_used=True, source_sha256=sha(Path(__file__)),
        previous_positions_sha256={c:sha(iteration.RAW/'single_curve_reentry'/(c+'_positions.json'))
                                   for c in read(iteration.RAW/'protocol.json')['cases']})
    if path.exists():
        if read(path) != protocol:
            raise ValueError('preserve frozen extension protocol')
    else:
        write(path, protocol)
    sys.argv = [sys.argv[0], '--stage', args.stage]
    engine.main()
    if args.stage == 'audit':
        with ProcessPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(auditor.nominations, protocol['cases']))
        write(OUT/'independent_nomination_audit.json', dict(rows=rows, all_passed=True))


if __name__ == '__main__':
    main()
