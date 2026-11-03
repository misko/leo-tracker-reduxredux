"""Bounded30worker full DS23 test of the frozen causal-neighbor mean rule."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import time

import probe_ds23_neighbor_phase_prior as prior
import probe_ds23_neighbor_phase_position as position
import audit_ds23_neighbor_phase_position as audit
from probe_ds23_sign_carrier_position import SIGNED_AUDIT
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_neighbor_phase_full'
BULK = Path('/srv/bulk/leo/research/ds23-neighbor-phase-full-20261020')


def configure(cases):
    prior.OUT, prior.CASES = BULK/'priors', cases
    position.OUT, position.PRIORS, position.CASES = BULK/'position', BULK/'priors', cases
    audit.inference = position


def run(case):
    started = time.monotonic()
    def timeout(*_):
        raise TimeoutError('120second causal-neighbor full case budget exhausted')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(120)
    try:
        if not (prior.OUT/(case+'.json')).exists():
            hp, fp, history, forecast, prefix, full, location = prior.inputs(case)
            transitions = forecast['transitions']; boundary = forecast['temporal_split_boundary_ns']
            training = sum(r['validation_time_ns'] <= boundary and r['norad'] % 5 != 0 for r in transitions)
            future = sum(r['validation_time_ns'] > boundary and r['norad'] % 5 == 0 for r in transitions)
            if min(training, future) < 30:
                write(prior.OUT/(case+'.json'), dict(case=case,
                    selection=dict(qualified=False, reason='insufficient chronological or satellite-disjoint history',
                                   full=dict(kind=None, coefficient=0.)),
                    transitions=len(transitions), prefix_model=prefix, full_model=full, full_location=location,
                    history_sha256=sha(hp), forecast_sha256=sha(fp), all_TLE_versions_pre_scan=True,
                    no_RF_or_GPS_or_position_input=True, all_causal_candidates_used=True))
            else:
                prior.run(case)
        record = position.run(case)
        result = dict(case=case, status='complete', prior_qualified=record['prior_qualified'], paired_valid=record['paired_valid'],
                      position_sha256=sha(position.OUT/(case+'.json')), prior_sha256=sha(prior.OUT/(case+'.json')))
    except Exception as exc:
        result = dict(case=case, status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    result['seconds'] = time.monotonic()-started
    write(BULK/'receipts'/(case+'.json'), result)
    return result


def freeze():
    OUT.mkdir(exist_ok=True)
    for folder in ['priors', 'position', 'receipts']:
        (BULK/folder).mkdir(parents=True, exist_ok=True)
        link = OUT/folder
        if not link.exists():
            link.symlink_to(BULK/folder, target_is_directory=True)
    cases = sorted(read(SIGNED_AUDIT)['evidence'])
    protocol = dict(cases=cases, available=410, population=413,
        missing_cases=['DS23-0012', 'DS23-0184', 'DS23-0286'], workers=30, per_case_seconds=120,
        prototype_frozen_before_full_evaluation=True, full_population_includes_development_and_confirmation_cases=True,
        separate_fresh20_confirmation='reports/2026_10_20_ds23_neighbor_phase_confirmation/position/independent_replay_audit.json',
        sufficient_history_rule='at least30 training targets and30 later target-satellite-disjoint targets; otherwise exact incumbent',
        causal_TLE_only_prior_qualification=True, no_RF_GPS_or_position_target_in_prior_learning=True,
        same_site_not_new_location_validation=True, matched_c0_fitted_c=True,
        only_change='qualified neighbor forecast added to existing phase means; unchanged variances, observations, gates and aliases',
        regional_center=[37.906, -122.545], regional_box_km=25, cold_start=[0, 0], phase_rounds=5, position_iterations=48,
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_neighbor_phase_forecast.py',
            ROOT/'tools/probe_ds23_neighbor_phase_prior.py', ROOT/'tools/probe_ds23_neighbor_phase_position.py',
            ROOT/'tools/audit_ds23_neighbor_phase_position.py']})
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('full neighbor protocol changed')
    if not path.exists():
        write(path, protocol)
    configure(cases)
    # The shared audit consumes this bound inference protocol next to positions.
    target = position.OUT/'protocol.json'
    if target.exists() and read(target) != protocol:
        raise ValueError('full neighbor position protocol changed')
    if not target.exists():
        write(target, protocol)
    return protocol


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['run', 'audit'], required=True); args = parser.parse_args()
    protocol = freeze()
    if args.stage == 'audit':
        audit.report()
        return
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=30) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run, c) for c in protocol['cases']])]
    result = dict(rows=rows, all_terminal=True, elapsed_seconds=time.monotonic()-started,
                  failures=[r for r in rows if r['status'] != 'complete'], protocol_sha256=sha(OUT/'protocol.json'))
    write(OUT/'execution.json', result)
    print('NEIGHBOR_FULL_TERMINAL', dict(count=len(rows), failures=len(result['failures']), seconds=result['elapsed_seconds']), flush=True)


if __name__ == '__main__':
    main()
