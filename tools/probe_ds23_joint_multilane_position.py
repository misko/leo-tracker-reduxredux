"""Joint curved versus cut-predictive inference on the same all-lane RF data."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_joint_multilane_calibration import joint_multilane_problem
from probe_ds23_joint_probe_position import endpoint
from probe_ds23_multilane_position import prepare_inputs, OUT as PREVIOUS
from probe_ds23_frequency_events import cached
from investigate_dsx01_localization_failures import fit
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = PREVIOUS.parent/'joint_position'
METHODS = ('joint_independent_all_lanes', 'joint_shared_all_lanes')


def make(d, arm, reference, extra, correlated):
    return cached(joint_multilane_problem(d, arm, reference, extra, correlated))


def refit(d, arm, extra, correlated):
    position, reference, history = np.zeros(2), np.zeros(len(d['means'])), []
    for _ in range(5):
        p = make(d, arm, reference, extra, correlated)
        result = fit(p, position, iterations=48); position = np.asarray(result['parameters'])
        phase = np.clip(p.state(position)['phases'][p.labels], -15, 15)
        history.append(dict(fit=result, phase_change_s=float(np.max(abs(phase-reference)))))
        reference = phase
    record = endpoint(p, position)
    record.update(history=history, final_phase_change_s=history[-1]['phase_change_s'])
    return record


def run(case):
    path = OUT/(case+'.json')
    if path.exists():
        return read(path)
    started = time.monotonic()
    def timeout(*_):
        raise TimeoutError('300 second joint all-lane pilot budget exhausted')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(300)
    try:
        d = prepare_inputs(case); old = read(PREVIOUS/(case+'.json'))
        if old['status'] != 'complete':
            raise ValueError('all-lane evidence unavailable')
        results = {}
        for method in METHODS:
            pair = {a: refit(d, a, old['extra_entries'], method == 'joint_shared_all_lanes') for a in ARMS}
            accepted = valid(pair)
            results[method] = dict(arms=pair, paired_valid=accepted, policy_arms=pair if accepted else d['signed']['policy_arms'])
            print(case, method, 'valid', accepted, {a: r['endpoint_east_north_km'] for a, r in pair.items()}, flush=True)
        record = dict(case=case, status='complete', results=results, extra_entries=old['extra_entries'],
                      previous_sha256=sha(PREVIOUS/(case+'.json')), original_observations_priors_and_gates_retained=True,
                      no_linear_calibration=True, no_GPS_inference=True, same_covariance_data_and_c_pair=True,
                      empirical_conditional_Gamma_model_not_calibrated_RF_density=True)
    except Exception as exc:
        import traceback
        traceback.print_exc(); record = dict(case=case, status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    record['seconds'] = time.monotonic()-started; write(path, record)
    return record


def main():
    OUT.mkdir(exist_ok=True); cases = read(PREVIOUS/'protocol.json')['cases']
    protocol = dict(cases=cases, methods=list(METHODS), matched_c0_fitted_c=True, phase_rounds=5, iterations=48,
        cold_regional_start=[0, 0], region_width_km=25, workers=3, per_case_seconds=300,
        original_observations_and_gates_preserved=True, independent_curvature_required_for_calibration=True,
        new_power='minimum existing primary anchor and secondary family powers', no_GPS_used=True,
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_joint_multilane_calibration.py']},
        previous_protocol_sha256=sha(PREVIOUS/'protocol.json'))
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('joint all-lane protocol changed')
    if not path.exists():
        write(path, protocol)
    with ProcessPoolExecutor(max_workers=3) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run, c) for c in cases])]
    write(OUT/'execution.json', dict(rows=rows, all_terminal=True))


if __name__ == '__main__':
    main()
