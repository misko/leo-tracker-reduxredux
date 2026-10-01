"""Four predeclared correlation times, fixed states/identities, donor-only selection."""
import fcntl
import json
from pathlib import Path
import sys
import numpy as np
from denser_window_inputs import prepare_denser_window
from denser_track_ports import build_ports
from conditional_track_evidence import nested_transform, conditional_student
from regression_batch import verify_sources
from screen_seed_prefix import digest, sealed

HERE = Path(__file__).resolve().parent
TIMES = (.5, 2., 10., 60.)


def main():
    output = HERE/'added-covariance-screen-v1.json'
    if output.exists():
        raise FileExistsError(output)
    path = HERE/'added-track-evidence-v1.json'
    parent = sealed(path)
    verify_sources(parent['sources'])
    verify_sources(parent['inputs'])
    inputs = {str(path): digest(path), **parent['inputs']}
    rows, totals = [], {}
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for summary in parent['summary']:
            unit = summary['unit']
            receipt = sealed(HERE/'denser-pilot-v1'/unit/'8'/(unit+'.json'))
            prepared, _ = prepare_denser_window(unit, 8)
            scan, height, _ = prepared[1][0]
            old_ports, _ = build_ports(scan, height, 8)
            dense_ports, _ = build_ports(scan, height, 16)
            state = np.asarray(receipt['best']['mean'])
            sums = {str(t): 0. for t in TIMES}
            for saved in [r for r in parent['rows'] if r['unit'] == unit]:
                i, candidate = saved['track_index'], saved['candidate_index']
                old, port = old_ports[i], dense_ports[i]
                prediction = port.predict_selected(state, candidate)
                assert prediction.eligible
                transform, _ = nested_transform(old.observation_ids, port.observation_ids,
                    old.likelihood.contrasts, port.likelihood.contrasts)
                contrast = transform@port.likelihood.contrasts
                residual = transform@(port.observation-prediction.mean)
                times = port.likelihood.times
                lag = np.abs(times[:, None]-times[None, :])
                scores = {}
                for tau in TIMES:
                    raw = scan.config.white_noise_hz**2*np.eye(len(times))+scan.config.correlated_noise_hz**2*np.exp(-lag/tau)
                    scale = contrast@raw@contrast.T
                    result = conditional_student(residual, (scale+scale.T)/2, len(old.observation))
                    assert abs(result['log_density']-result['log_ratio']) < 1e-8
                    if tau == .5:
                        assert scan.config.correlation_time_s == tau
                        assert abs(result['log_density']-saved['log_predictive_density']) < 1e-8
                    scores[str(tau)] = result['log_density']
                    sums[str(tau)] += result['log_density']
                rows.append(dict(unit=unit, track_index=i, added_count=saved['added_count'], scores=scores))
            totals[unit] = dict(added_count=summary['added_observations'], scores=sums,
                mean_scores={k: v/summary['added_observations'] for k, v in sums.items()})
    selected = []
    for target in totals:
        donors = [u for u in totals if u != target]
        donor_scores = {str(t): float(np.mean([totals[u]['mean_scores'][str(t)] for u in donors])) for t in TIMES}
        chosen = max(TIMES, key=lambda t: donor_scores[str(t)])
        selected.append(dict(target=target, donors=donors, correlation_time_s=chosen, donor_scores=donor_scores,
            target_gain_nats_per_added_observation=totals[target]['mean_scores'][str(chosen)]-totals[target]['mean_scores']['0.5']))
    sources = {str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py'
        and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
    sources[str(HERE/'ADDED_COVARIANCE_SCREEN_PLAN.md')] = digest(HERE/'ADDED_COVARIANCE_SCREEN_PLAN.md')
    result = dict(totals=totals, selected=selected, rows=rows, sources=sources, inputs=inputs,
        qualification='Fixed eight-point fitted states/identities; no fits or reference scoring. Only correlation time changes. Donor selection excludes target added observations; not geographic validation or marginalized state uncertainty.')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(dict(totals=totals, selected=selected), indent=2))


if __name__ == '__main__':
    main()
