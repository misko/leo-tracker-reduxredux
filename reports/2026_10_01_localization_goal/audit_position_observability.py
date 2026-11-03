"""Position information after nuisance projection at frozen baseline states."""
import json
import time
from pathlib import Path

import numpy as np

from acquisition_dot import prepare
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def projected_information(position, nuisance, tolerance=1e-10):
    """Stable projection with normalized nuisance columns and rank reporting."""
    norms = np.linalg.norm(nuisance, axis=0)
    active = norms > 0
    scaled = nuisance[:, active]/norms[active]
    u, singular, _ = np.linalg.svd(scaled, full_matrices=False)
    rank = int(np.sum(singular > tolerance*singular[0])) if len(singular) else 0
    residual = position-u[:, :rank]@(u[:, :rank].T@position)
    return residual.T@residual, rank, singular


def retention(information, reference):
    lower = np.linalg.cholesky(reference)
    transformed = np.linalg.solve(lower, information)
    transformed = np.linalg.solve(lower, transformed.T).T
    return np.linalg.eigvalsh((transformed+transformed.T)/2)


def main():
    started = time.monotonic()
    selection = HERE/'split-expansion-fit-v1/sources.json'
    assert digest(selection) == selection.with_suffix('.sha256').read_text().strip()
    sources = {str(Path(__file__)): digest(__file__)}
    inputs, rows = {str(selection): digest(selection)}, []
    for unit in json.loads(selection.read_text())['units']:
        path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
        assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())['prediction_sha256']
        receipt = json.loads(path.read_text())
        verify_sources(receipt['source_sha256'])
        verify_sources(receipt['inputs'])
        sources.update(receipt['source_sha256'])
        inputs[str(path)] = digest(path)
        scan, height, ports = prepare(unit)
        assert height.input_bindings == receipt['height']
        assert [list(p.observation_ids) for p in ports] == receipt['observations']
        state = np.asarray(receipt['best']['mean'])
        assignments = [int(np.argmax(p.score_all(state))) for p in ports]
        epochs = sorted({5+i for p, i in zip(ports, assignments, strict=True) if i < p.candidate_count})
        columns = [0, 1, 2, 3, 4, *epochs]
        blocks = []
        for port, identity in zip(ports, assignments, strict=True):
            if identity == port.candidate_count:
                continue
            prediction = port.predict_selected(state, identity)
            residual = port.observation-prediction.mean
            solved = np.linalg.solve(prediction.covariance, residual)
            weight = (4+len(residual))/(4+float(residual@solved))
            blocks.append(np.sqrt(weight)*np.linalg.solve(np.linalg.cholesky(prediction.covariance),
                                                          prediction.jacobian[:, columns]))
        jacobian = np.vstack(blocks)
        a, b = jacobian[:, :2], jacobian[:, 2:]
        fixed = a.T@a
        free, rank, singular = projected_information(a, b)
        free_loose, loose_rank, _ = projected_information(a, b, 1e-8)
        assert loose_rank == rank
        assert np.max(abs(free-free_loose)) < 1e-8
        precision = np.r_[1., np.full(len(columns)-3, 4.)]
        augmented_a = np.vstack([a, np.zeros((len(precision), 2))])
        augmented_b = np.vstack([b, np.diag(np.sqrt(precision))])
        regularized, _, _ = projected_information(augmented_a, augmented_b)
        schur = a.T@a-a.T@b@np.linalg.solve(b.T@b+np.diag(precision), b.T@a)
        assert np.linalg.norm(regularized-schur) < 1e-7*max(1., np.linalg.norm(regularized))
        eig, vectors = np.linalg.eigh(regularized)
        retain = retention(free, regularized)
        assert np.all(retain >= -1e-8) and np.all(retain <= 1+1e-8)
        rows.append(dict(unit=unit, track_count=len(ports), assigned_tracks=len(blocks),
            active_satellites=len(epochs), observations=len(jacobian),
            nuisance_columns=b.shape[1], data_nuisance_rank=rank,
            nuisance_singular_values=singular.tolist(),
            position_information_fixed=fixed.tolist(), position_information_with_priors=regularized.tolist(),
            position_information_free_nuisance=free.tolist(),
            free_vs_prior_retention=retain.tolist(), prior_vs_fixed_retention=retention(regularized, fixed).tolist(),
            local_prior_inverse_curvature_axes_m=(1000/np.sqrt(eig)).tolist(),
            weak_direction_enu=vectors[:, 0].tolist(),
            schur_projection_difference=float(np.max(abs(regularized-schur)))))
    verify_sources(sources)
    verify_sources(inputs)
    result = dict(rows=rows, source_sha256=sources, input_sha256=inputs,
        seconds=time.monotonic()-started,
        median_worst_direction_retention=float(np.median([r['free_vs_prior_retention'][0] for r in rows])),
        median_best_direction_retention=float(np.median([r['free_vs_prior_retention'][1] for r in rows])),
        qualification='Fixed baseline states and hard identities; positive IRLS quadratic, not '
        'observed Hessian, global identifiability, or calibrated covariance. Nuisance column '
        'normalization makes rank tests invariant to coordinate scaling. Two tolerances checked; '
        'prior-augmented projection independently agrees with Schur elimination. Local support '
        'and assignments held fixed. No reference coordinate, new fit, GPS or RF.')
    output = HERE/'position-observability-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ['rows', 'source_sha256', 'input_sha256']}, indent=2))


if __name__ == '__main__':
    main()
