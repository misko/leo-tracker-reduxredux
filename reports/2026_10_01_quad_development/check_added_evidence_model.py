"""Model-matched conditional simulation; account for covariance before interpreting signs."""
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


def interval(values):
    return dict(mean=float(np.mean(values)), q025=float(np.percentile(values, 2.5)),
                median=float(np.median(values)), q975=float(np.percentile(values, 97.5)))


def main():
    output = HERE/'added-evidence-model-check-v1.json'
    if output.exists():
        raise FileExistsError(output)
    path = HERE/'added-track-evidence-v1.json'
    parent = sealed(path)
    verify_sources(parent['sources'])
    verify_sources(parent['inputs'])
    rows = []
    draws = 2000
    rng = np.random.default_rng(801604)
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for summary in parent['summary']:
            unit = summary['unit']
            receipt = sealed(HERE/'denser-pilot-v1'/unit/'8'/(unit+'.json'))
            prepared, _ = prepare_denser_window(unit, 8)
            scan, height, _ = prepared[1][0]
            eight, _ = build_ports(scan, height, 8)
            dense, _ = build_ports(scan, height, 16)
            state = np.asarray(receipt['best']['mean'])
            squared, excess = np.zeros(draws), np.zeros(draws)
            count, eligible = 0, 0
            for saved in [r for r in parent['rows'] if r['unit'] == unit]:
                i, candidate = saved['track_index'], saved['candidate_index']
                old, port = eight[i], dense[i]
                prediction = port.predict_selected(state, candidate)
                assert prediction.eligible, 'Fixed identity loses dense visibility support'
                eligible += 1
                transform, _ = nested_transform(old.observation_ids, port.observation_ids,
                    old.likelihood.contrasts, port.likelihood.contrasts)
                residual = transform@(port.observation-prediction.mean)
                scale = transform@prediction.covariance@transform.T
                result = conditional_student(residual, (scale+scale.T)/2, len(old.observation))
                degrees = result['degrees']
                sd = np.sqrt(degrees/(degrees-2)*np.diag(result['scale']))
                assert np.allclose(result['innovation']/sd, saved['standardized_innovations'], rtol=0, atol=1e-8)
                k = len(sd)
                simulated = rng.normal(size=(draws, k))@np.linalg.cholesky(result['scale']).T
                simulated /= np.sqrt(rng.chisquare(degrees, size=draws)/degrees)[:, None]
                simulated /= sd
                squared += np.sum(simulated**2, axis=1)
                signs = simulated > 0
                same = np.sum(signs[:, 1:] == signs[:, :-1], axis=1)
                positive = signs.sum(axis=1)
                # Expected equal-sign pairs after within-track permutation.
                shuffled = (positive*(positive-1)+(k-positive)*(k-positive-1))/k
                excess += same-shuffled
                count += k
            assert count == summary['added_observations']
            rows.append(dict(unit=unit, eligible_checked_tracks=eligible, added_observations=count,
                observed_standardized_rms=summary['standardized_rms'],
                simulated_standardized_rms=interval(np.sqrt(squared/count)),
                observed_sign_excess=summary['same_sign_pairs']-summary['shuffle_expected_same_sign_pairs'],
                simulated_sign_excess=interval(excess)))
    sources = {str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py'
        and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
    result = dict(rows=rows, draws=draws, seed=801604, sources=sources,
        inputs={str(path): digest(path), **parent['inputs']},
        qualification='Conditional model simulation at fixed fitted eight-point states/identities; preserves each added-block covariance and Student shared scale. Tracks conditionally independent as in model. Descriptive model checks, not independent significance tests or marginal state uncertainty.')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
