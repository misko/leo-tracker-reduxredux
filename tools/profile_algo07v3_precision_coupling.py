"""Observe the original precision map's local sensitivity; never change inference.

Every saved transition must match before finite-difference diagnostics proceed.
Jacobians describe local update dynamics, not localization accuracy or speedup.
"""

import argparse
import ast
import copy
import hashlib
import inspect
import json
import os
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import hierarchical


def factory():
    source = inspect.getsource(hierarchical.hierarchical_bound)
    tree = ast.parse(source)
    function = tree.body[0]
    loops = [(i,n) for i,n in enumerate(function.body)
             if isinstance(n, ast.For) and ast.unparse(n.iter)=='range(iterations)']
    if len(loops) != 1:
        raise ValueError('Review changed precision loop')
    index, loop = loops[0]
    updates = [i for i,n in enumerate(loop.body) if isinstance(n, ast.Assign)
               and ast.unparse(n.targets[0])=='(rate, prior_rate)']
    if len(updates) != 1:
        raise ValueError('Review changed precision update')
    transition = ast.parse('def transition(rate, prior_rate):\n    pass').body[0]
    transition.body = copy.deepcopy(loop.body[:updates[0]])
    transition.body.append(ast.parse('return next_rate, next_prior_rate, change').body[0])
    setup = function.body[:index]
    seeded_precision = any(isinstance(n, ast.Assign) and
                           any(isinstance(t, ast.Name) and t.id == 'precision' for t in n.targets)
                           for n in setup)
    if seeded_precision:
        # Extracting a conditional assignment makes precision local to the new
        # function. Recreate its original pre-loop value on every diagnostic call.
        setup += ast.parse('_transition_initial_precision = precision.copy()').body
        transition.body[:0] = ast.parse('precision = _transition_initial_precision.copy()').body
    function.body = setup + [transition, ast.parse('return transition').body[0]]
    tree = ast.fix_missing_locations(tree)
    scope = dict(vars(hierarchical))
    exec(compile(tree, '<precision-map-observer>', 'exec'), scope)
    return scope['hierarchical_bound'], source, ast.unparse(tree)


def jacobian(transition, rate, prior_rate, epsilon):
    n = len(rate)
    state = np.log(np.r_[rate, prior_rate])
    matrix = np.empty((len(state), len(state)))
    for column in range(len(state)):
        left, right = state.copy(), state.copy()
        left[column] -= epsilon
        right[column] += epsilon
        def evaluate(x):
            next_rate, next_prior, _ = transition(np.exp(x[:n]), np.exp(x[n:]))
            return np.log(np.r_[next_rate, next_prior])
        matrix[:,column] = (evaluate(right)-evaluate(left))/(2*epsilon)
    return matrix


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--trajectory', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        p.error('One CPU and one BLAS thread required')
    if args.output.resolve().is_relative_to('/mnt/qnap01'):
        p.error('QNAP is read-only')
    args.output.mkdir(exist_ok=False)
    meta_path, raw = args.capture/'hardest.json', args.capture/'hardest.npz'
    metadata = json.loads(meta_path.read_bytes())
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == metadata['arrays_sha256']
    with np.load(raw, allow_pickle=False) as archive:
        positional = [archive[f'argument_{i}'] for i in range(4)]
        keywords = dict(metadata['scalar_keywords'])
        keywords.update({k.removeprefix('keyword_'): archive[k] for k in archive.files
                         if k.startswith('keyword_')})
    paths = [Path(__file__), Path(hierarchical.__file__), meta_path, raw, args.trajectory,
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(q.resolve()):hashlib.sha256(q.read_bytes()).hexdigest() for q in paths}
    saved = json.loads(args.trajectory.read_bytes())
    assert saved['exact'] and saved['unchanged_inputs']
    assert saved['bindings'][str(raw.resolve())] == metadata['arrays_sha256']
    make, original, generated = factory()
    (args.output/'original.py').write_text(original.rstrip()+'\n')
    (args.output/'generated.py').write_text(generated.rstrip()+'\n')
    before = fingerprint((positional, keywords))
    transition = make(*positional, **keywords)
    for row in saved['rows']:
        actual = transition(np.array(row['rate']), np.array(row['prior_rate']))
        expected = (np.array(row['next_rate']), np.array(row['next_prior_rate']), row['change'])
        assert fingerprint(actual) == fingerprint(expected)
    changes = np.array([r['change'] for r in saved['rows']])
    chosen = sorted({int(changes.argmin()), len(changes)-1})
    results = []
    matrices = {}
    for index in chosen:
        row = saved['rows'][index]
        rate, prior = np.array(row['rate']), np.array(row['prior_rate'])
        for epsilon in (1e-3, 3e-4, 1e-4):
            matrix = jacobian(transition, rate, prior, epsilon)
            eigenvalues, vectors = np.linalg.eig(matrix)
            dominant = int(abs(eigenvalues).argmax())
            vector = abs(vectors[:,dominant])
            vector /= vector.max()
            top = np.argsort(vector)[::-1][:6]
            results.append(dict(iteration=index, epsilon=epsilon,
                                spectral_radius=float(abs(eigenvalues[dominant])),
                                eigen_real=float(eigenvalues[dominant].real),
                                eigen_imag=float(eigenvalues[dominant].imag),
                                dominant_components=[dict(index=int(i), relative=float(vector[i]))
                                                     for i in top]))
            matrices[f'iteration_{index}_epsilon_{epsilon}'] = matrix
    assert before == fingerprint((positional, keywords))
    assert all(hashlib.sha256(Path(q).read_bytes()).hexdigest()==h for q,h in bindings.items())
    np.savez(args.output/'jacobians.npz', **matrices)
    result = dict(bindings=bindings, exact_transition_count=len(saved['rows']),
                  unchanged_inputs=True, results=results,
                  noise_groups=len(saved['rows'][0]['rate']),
                  learned_prior_groups=len(saved['rows'][0]['prior_rate']),
                  jacobians_sha256=hashlib.sha256((args.output/'jacobians.npz').read_bytes()).hexdigest(),
                  inference_modified=False, full_pipeline_speedup=None)
    (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['results'], indent=2))


if __name__ == '__main__':
    main()
