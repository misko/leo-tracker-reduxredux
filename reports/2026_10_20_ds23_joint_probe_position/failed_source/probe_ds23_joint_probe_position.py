"""Joint conditional curved-evidence tests with a frozen RF-only eligibility rule."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import time
import numpy as np

from compare_dsx01_frame_joint import conditional_gate
from ds23_joint_probe_calibration import joint_problem, curved_entries
from ds23_same_probe_covariance import residual_pair
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import cached, summary
from probe_ds23_shared_probe_cohort import BULK, OUT as CONFIRMATION
import probe_ds23_shared_probe_position as original
from run_algo01_ds23_sample import ROOT, read, write, sha
from run_ds23_combined_recovery_full import ARMS, valid
from leo.analysis.research.retained_track_likelihood import profile
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

OUT = ROOT/'reports/2026_10_20_ds23_joint_probe_position'
METHODS = ('joint_independent_curved', 'joint_shared_curved')


def RF_guard(case):
    rows = sorted([r for r in read(original.RF/'evaluation.json')['rows'] if r['case'] == case and r['two_components_qualified']], key=lambda r: r['time_s'])
    degree = read(original.RF/'evaluation.json')['summary'][case]['RF_qualified']['degree']
    t = np.array([r['time_s'] for r in rows]); one = np.array([r['refined_first_value'] for r in rows]); two = np.array([r['refined_second_value'] for r in rows])
    statistics = residual_pair(t, one, two, degree)
    interleaved = [residual_pair(t[k::2], one[k::2], two[k::2], degree)['correlation'] for k in (0, 1)]
    noise = [bool(batch_noise_screen(np.array(statistics[name])[None], t)['noise_screen_pass'][0])
             for name in ('first_residual_hz', 'second_residual_hz')]
    checks = dict(correlation_at_least_point6=statistics['correlation'] >= .6,
                  both_interleaved_at_least_point4=min(interleaved) >= .4,
                  both_original_residual_noise_screens_pass=all(noise))
    return dict(eligible=all(checks.values()), checks=checks, correlation=statistics['correlation'],
                interleaved_correlations=interleaved, degree=degree)


def configure(case):
    if case in original.CASES:
        original.RF = ROOT/'reports/2026_10_20_ds23_same_probe_IQ'
        original.CATALOGUE = ROOT/'reports/2026_10_20_ds23_differential_catalogue'
        return ROOT/'reports/2026_10_20_ds23_shared_probe_position'
    original.RF = BULK/'IQ'
    original.CATALOGUE = BULK/'catalogue'
    return BULK/'position'


def gates(p, position):
    c = p.calculate(position); records = []
    for k, (entry, sl) in enumerate(zip(p.joint_secondary_entries, p.joint_secondary_slices, strict=True)):
        track = p.scan.tracks[entry['track_index']]
        profiles = {}
        for name in ('conditional', 'marginal'):
            raw = c['joint_secondary_'+name+'_raw_hz'][sl]
            fitted = profile(raw, np.zeros(len(raw)), *p.scan.white[entry['track_index']], bias_sigma=300.)
            noise = batch_noise_screen(fitted['innovations'], track['times'])
            profiles[name] = dict(rms_hz=float(fitted['rms'][0]), bias_hz=float(fitted['bias'][0]),
                                  alias=int(fitted['alias'][0]), noise_screen_pass=bool(noise['noise_screen_pass'][0]),
                                  diagnostics={key: value[0] for key, value in noise.items()})
        conditional = conditional_gate(c['joint_secondary_fitted_residual_hz'][sl], track['times'])
        compatible = conditional['compatible'] and c['joint_secondary_elevation'][sl].min() >= 0
        compatible = compatible and all(r['rms_hz'] <= 450 and abs(r['bias_hz']) <= 3000 and r['alias'] == 0
                                       and r['noise_screen_pass'] for r in profiles.values())
        records.append(dict(component=entry['component'], candidate_index=entry['candidate_index'], norad=entry['norad'],
                            points=entry['points'], observation_ids=entry['observation_ids'], compatible=bool(compatible),
                            profile=profiles, conditional_residual_gate=conditional,
                            noise_precision=float(c['joint_secondary_noise_precision'][k]),
                            fitted_bias_hz=float(c['joint_secondary_bias_hz'][k])))
    return records


def make(d, arm, reference, extra, correlated):
    return cached(joint_problem(d['enriched'], d['node'], d['mask'], arm, reference, d['powers'], d['means'], d['hyper'],
        d['original_entries'], extra, d['anchors'], d['covariance'], correlated))


def endpoint(p, position):
    record = summary(p, position, p.linear_entries)
    record['joint_secondary_gates'] = gates(p, position)
    record['gates']['tracks'] += record['joint_secondary_gates']
    record['additional_curved_points'] = sum(e['points'] for e in p.joint_secondary_entries)
    record['conditional_powers'] = p.joint_conditional_powers
    return record


def refit(d, arm, extra, correlated):
    position, reference, history = np.zeros(2), np.zeros(len(d['means'])), []
    for _ in range(5):
        p = make(d, arm, reference, extra, correlated)
        result = fit(p, position, iterations=48)
        position = np.asarray(result['parameters'])
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
    started = time.monotonic(); source = configure(case)
    previous = read(source/(case+'.json'))
    def timeout(*_):
        raise TimeoutError('240 second joint conditional position budget exhausted')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(240)
    result = dict(case=case, previous_position_sha256=sha(source/(case+'.json')))
    try:
        guard = RF_guard(case); result['RF_guard'] = guard
        if not guard['eligible']:
            result.update(status='no_offer', reason='RF common-error eligibility failed')
        elif previous['status'] != 'complete':
            result.update(status='no_offer', reason='no stable original simultaneous nomination/support', previous_error=previous.get('error'))
        else:
            d = original.prepare_inputs(case)
            extra = previous['extra_entries']
            calibration, predictive, diagnostics = curved_entries(d['enriched'], extra, d['covariance'])
            if not calibration:
                result.update(status='no_offer', reason='no independently active curved secondary evidence')
            else:
                methods = {}
                for method in METHODS:
                    arms = {a: refit(d, a, extra, method == 'joint_shared_curved') for a in ARMS}
                    accepted = valid(arms)
                    methods[method] = dict(arms=arms, paired_valid=accepted,
                        policy_arms=arms if accepted else d['signed']['policy_arms'])
                    print(case, method, 'paired_valid', accepted,
                          {a: r['endpoint_east_north_km'] for a, r in arms.items()}, flush=True)
                result.update(status='complete', results=methods, curvature_evidence=diagnostics, extra_entries=extra,
                              incumbent_arms=d['signed']['policy_arms'], covariance=d['covariance'],
                              promoted_curved_components=[e['component'] for e in calibration],
                              predictive_only_components=[e['component'] for e in predictive],
                              original_observations_and_powers_retained=True, original_gates_unchanged=True,
                              no_GPS_inference=True, linear_points_never_calibrate=True,
                              original_phase_priors_unchanged=True, empirical_conditional_model_not_calibrated_full_RF_density=True)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result.update(status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    result['seconds'] = time.monotonic()-started
    write(path, result)
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cases = list(original.CASES)+read(CONFIRMATION/'selection.json')['cases']
    protocol = dict(cases=cases, previous_two_plus20_are_development_for_this_new_variant=True,
                    methods=list(METHODS), RF_guard=dict(correlation=.6, minimum_interleaved=.4, both_residual_noise_screens=True),
                    active_curvature='existing polynomial_screen: >=8 points, >=20s, degree<=4, BICgain>=10, linear_RMS>=250Hz, original noise gate',
                    new_bias_sigma_hz=300, old_powers_unchanged=True, new_power='minimum existing primary-anchor and secondary-family powers',
                    matched_c0_fitted_c=True, cold_regional_start=[0, 0], region_width_km=25,
                    phase_rounds=5, position_iterations=48, per_case_seconds=240, workers=8,
                    causal_TLEs_and_historical_priors_unchanged=True, no_GPS_used=True,
                    source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_joint_probe_calibration.py']})
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('joint conditional protocol changed')
    if not path.exists():
        write(path, protocol)
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run, c) for c in cases])]
    write(OUT/'execution.json', dict(rows=rows, all_terminal=True))


if __name__ == '__main__':
    main()
