"""Check the clock/epoch likelihood ambiguity and conditional prior curvature."""
import json
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def prior_terms(clock, totals, heavy):
    """Conditional negative log prior, derivative, exact and IRLS curvature.

    Constants independent of clock are omitted. Clock variance=1 second^2;
    epoch variance=.25 second^2, Gaussian or t4 with scale matrix=.125.
    """
    epochs = np.asarray(totals)-clock
    if heavy:
        value = .5*clock**2+2.5*np.log1p(epochs**2/.5).sum()
        gradient = clock-np.sum(5*epochs/(.5+epochs**2))
        curvature = 1+np.sum(5*(.5-epochs**2)/(.5+epochs**2)**2)
        irls = 1+np.sum(5/(.5+epochs**2))
    else:
        value = .5*clock**2+2*np.sum(epochs**2)
        gradient = clock-4*np.sum(epochs)
        curvature = irls = 1+4*len(epochs)
    return np.array([value, gradient, curvature, irls], dtype=float)


def conditional_minima(totals, clock, heavy):
    # All conditional minima better than this point lie within this bound:
    # omitted-constant objective >= clock^2/2. The grid is a diagnostic search,
    # not a proof that every stationary point was enumerated.
    bound = max(1., np.sqrt(2*prior_terms(clock, totals, heavy)[0]))
    grid = np.linspace(-bound, bound, 2049)
    gradients = [prior_terms(c, totals, heavy)[1] for c in grid]
    roots = []
    for low, high, gl, gh in zip(grid[:-1], grid[1:], gradients[:-1], gradients[1:], strict=True):
        if gl <= 0 <= gh:
            for _ in range(45):
                mid = .5*(low+high)
                if prior_terms(mid, totals, heavy)[1] < 0:
                    low = mid
                else:
                    high = mid
            root = .5*(low+high)
            roots.append(dict(clock_s=root, prior_terms=prior_terms(root, totals, heavy).tolist()))
    return roots


def main():
    original = HERE/'regression-v1-freeze.json'
    assert digest(original) == original.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(original.read_text())['source_sha256'])
    warm_freeze = HERE/'epoch-prior-warm-v1/sources.json'
    verify_sources(json.loads(warm_freeze.read_text())['source_sha256'])
    rows = []
    for unit in ['DS9-F001', 'DS10-F056', 'DS11-F001']:
        scan, height, ports = prepare(unit)
        for arm in ['gaussian', 'student']:
            path = HERE/'epoch-prior-warm-v1'/(unit+'-'+arm+'.json')
            assert digest(path) == path.with_suffix('.sha256').read_text().strip()
            receipt = json.loads(path.read_text())
            assert scan.inputs == receipt['inputs'] and height.input_bindings == receipt['height']
            assert [list(p.observation_ids) for p in ports] == receipt['observations']
            state = np.asarray(receipt['mean'])
            labels = np.asarray(receipt['labels'], dtype=int)
            assigned = receipt['assignments']
            terms = prior_terms(state[2], state[2]+state[5+labels], arm == 'student')
            changes, jacobian_null = [], 0.
            for offset in [-1., -.25, .25, 1.]:
                trial = state.copy()
                trial[2] += offset
                trial[5+labels] -= offset
                differences, score_differences = [], []
                for port, index in zip(ports, assigned, strict=True):
                    score_differences.append(abs(port.score_selected(trial, index)
                                                 -port.score_selected(state, index)))
                    if index < port.candidate_count:
                        a = port.predict_selected(state, index)
                        b = port.predict_selected(trial, index)
                        differences.append(float(np.max(np.abs(a.mean-b.mean))))
                        jacobian_null = max(jacobian_null, float(np.max(np.abs(
                            a.jacobian[:, 2]-a.jacobian[:, 5+index]))))
                changes.append(dict(offset_s=offset, maximum_mean_change_hz=max(differences),
                                    maximum_selected_score_change=max(score_differences)))
            minima = conditional_minima(state[2]+state[5+labels], state[2], arm == 'student')
            best = min(minima, key=lambda r: r['prior_terms'][0])
            rows.append(dict(
                unit=unit, arm=arm, parent_sha256=digest(path),
                parent_converged=receipt['converged'],
                clock_s=float(state[2]), satellite_groups=len(labels),
                prior_terms=dict(zip(['value', 'gradient', 'exact_curvature', 'irls_curvature'],
                                     terms.tolist(), strict=True)),
                conditional_minima=minima, best_clock_shift_s=best['clock_s']-float(state[2]),
                conditional_prior_gain=float(terms[0]-best['prior_terms'][0]),
                maximum_jacobian_null_hz_per_s=jacobian_null, invariance=changes))
    result = dict(
        source_sha256={str(p): digest(p) for p in [Path(__file__), original, warm_freeze]},
        rows=rows, qualification='Fixed-assignment gauge diagnostic, not a location refit. '
        'No GPS, no new candidate accepted. Selected signal means depend on clock+epoch; '
        'background visibility and alternative associations need not share that invariance. '
        'One-dimensional conditional prior minima use a bounded grid/root search, not a global '
        'proof. Original failed Student DS10 candidate remains failed.')
    output = HERE/'clock-epoch-gauge-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps([{k: v for k, v in r.items() if k not in ['invariance', 'conditional_minima']}
                      for r in rows], indent=2))


if __name__ == '__main__':
    main()
