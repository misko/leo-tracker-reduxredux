"""Run the next bounded worst-two DBG01 batch with unchanged ALGO02/03 engines."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from pathlib import Path
import sys

import probe_ds23_worst_association_bottleneck as baseline
import plot_ds23_worst_association_bottleneck as raw_figures
import probe_ds23_single_curved_reentry as reentry
import probe_ds23_support_aware_reentry as support
import finalize_ds23_support_reentry as finalize
import run_dbg01_latest_worst as dbg
import audit_ds23_worst_iteration as audit
import select_dbg01_regional_restart as restart_selection
from ds23_current_assignment_context import current_base_context
from run_algo01_ds23_sample import ROOT, read, sha, write

RAW = ROOT/'reports/2026_10_22_ds23_dbg01_iteration_002_raw'
CLOSED = ('DS23-0081', 'DS23-0326')
ORIGINAL_SETUP = baseline.setup


def current_setup(case):
    data = ORIGINAL_SETUP(case)
    current = baseline.build(data, 'c0', data['arms']['c0']['phase_reference'])
    return current_base_context(data, current)


def next_cases(rows, closed=CLOSED, count=2):
    ranked = baseline.select_worst(rows, len(rows))
    return [r['case'] for r in ranked if r['case'] not in set(closed)][:count]


def configure():
    baseline.OUT = raw_figures.OUT = RAW
    reentry.DEBUG, reentry.OUT = RAW, RAW/'single_curve_reentry'
    support.DEBUG, support.NOMINATIONS = RAW, reentry.OUT
    support.OUT = RAW/'support_aware_reentry'
    finalize.OLD, finalize.OUT = reentry.OUT, support.OUT
    dbg.PARENT, audit.OUT, audit.REENTRY = RAW, RAW, reentry.OUT
    for module in [baseline, raw_figures, reentry, support, finalize, dbg, audit]:
        module.setup = current_setup
    # The original plot mixed canonical and raw CFO gauges. Use the established
    # explicit-ID raw view after the inventory has been saved instead.
    baseline.plot = lambda *_: None


def protocol():
    RAW.mkdir(parents=True, exist_ok=True)
    cases = next_cases(list(csv.DictReader(baseline.BENCHMARK.open())))
    record = dict(iteration=2, context_version=2, cases=cases, previously_closed=list(CLOSED),
        initial_context_protocol_sha256=sha(RAW/'context_v1/protocol.json'),
        context_correction='bind diagnostic base rows to current family replacements before any ablation',
        context_helper_sha256=sha(ROOT/'tools/ds23_current_assignment_context.py'),
        benchmark_sha256=sha(baseline.BENCHMARK),
        debug_priority_only_uses_reported_position_error=True,
        inference_no_GPS_or_postscan_TLE=True,
        builds_on_existing_ALGO02_ALGO03=True,
        no_new_ALGO_release_without_full_DS23_confirmation=True,
        publish_all_iteration_results_including_negative=True,
        regional_center=[37.906, -122.545], regional_width_km=25.,
        regional_seeds=baseline.SEEDS.tolist(), saved_RF_endpoint_also_included=True,
        target_selection='three longest wholly unused actively curved tracks with at least12 points',
        prior_and_residual_gates_unchanged=True, both_c_arms=True,
        phase_screen='-15..15 seconds at1second coarse; hypotheses only',
        workers_DBG01=24, workers_case_nomination_and_fit=2,
        no_new_RF_no_stationary_pooling=True, source_sha256=sha(Path(__file__)),
        reused_source_sha256={m.__name__:sha(Path(m.__file__)) for m in
            [baseline, raw_figures, reentry, support, finalize, dbg, audit, restart_selection]})
    path = RAW/'protocol.json'
    if path.exists():
        if read(path) != record:
            raise ValueError('iteration protocol or source changed; preserve frozen evidence')
    else:
        write(path, record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    stages = ['inventory', 'screen', 'nominations', 'positions', 'reentry_audit',
              'support', 'support_finalize', 'dbg_prepare', 'dbg_audit_discover',
              'dbg_bank', 'dbg_analysis', 'independent_audit', 'restart_selection']
    parser.add_argument('--stage', choices=stages, required=True)
    args = parser.parse_args()
    configure()
    record = protocol()
    if args.stage in ['inventory', 'screen']:
        with ProcessPoolExecutor(max_workers=2) as pool:
            results = [f.result() for f in as_completed([
                pool.submit(baseline.one, case, args.stage) for case in record['cases']])]
        write(RAW/(args.stage+'_execution.json'), dict(rows=results, all_terminal=True,
            all_passed=all(r['status'] == 'complete' for r in results)))
        if args.stage == 'inventory' and all(r['status'] == 'complete' for r in results):
            for case in record['cases']:
                raw_figures.one(case)
    elif args.stage in ['nominations', 'positions', 'reentry_audit']:
        sys.argv = [sys.argv[0], '--stage', 'audit' if args.stage == 'reentry_audit' else args.stage]
        reentry.main()
    elif args.stage == 'support':
        support.main()
    elif args.stage == 'support_finalize':
        finalize.main()
    elif args.stage.startswith('dbg_'):
        sys.argv = [sys.argv[0], '--stage', args.stage[4:]]
        dbg.main()
    elif args.stage == 'independent_audit':
        audit.main()
    else:
        restart_selection.main()


if __name__ == '__main__':
    main()
