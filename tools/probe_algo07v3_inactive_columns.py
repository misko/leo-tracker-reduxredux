"""External posterior compression trial; full output exactness is mandatory."""

import argparse
import ast
import hashlib
import inspect
import json
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import hierarchical


def compact(gram, rhs, precision, covariance, active):
    width = len(rhs)
    indices = np.flatnonzero(active)
    selected = np.ix_(indices, indices)
    small = gram[selected]
    root = hierarchical._cholesky(small)
    n = len(indices)
    lu, pivots, info = hierarchical.dgetrf(root) if n else (root, None, 0)
    if info:
        raise np.linalg.LinAlgError('DGETRF failed')
    mean = np.zeros(width)
    if n:
        mean[indices] = hierarchical._solve_factor(root.T, np.arange(n, dtype=np.int32),
                            hierarchical._solve_factor(lu, pivots, rhs[indices]))
    if covariance:
        identity = np.eye(n, order='F')
        inv, info = (hierarchical.dgetrs(lu, pivots, identity, overwrite_b=1)
                     if n else (identity, 0))
        if info:
            raise np.linalg.LinAlgError('DGETRS failed')
        cov = np.eye(width)
        cov[selected] = inv.T@inv
        return mean, cov, None
    diagonal = np.ones(width)
    diagonal[indices] = np.diag(root)
    logdet = float(2*np.log(diagonal).sum())
    return mean, None, max(0., logdet-np.log(precision).sum())


def candidate():
    source = inspect.getsource(hierarchical.hierarchical_bound)
    tree = ast.parse(source)
    function = tree.body[0]
    posterior = next(n for n in function.body if isinstance(n, ast.FunctionDef)
                     and n.name=='posterior')
    root_index = next(i for i,n in enumerate(posterior.body) if isinstance(n, ast.Assign)
                      and ast.unparse(n.targets[0])=='root')
    # Preserve every grouped Gram/RHS accumulation. Only the subsequent solve
    # is compressed, and only when all coefficient priors remain fixed unit normals.
    fast = ast.parse('''if not np.any(selected) and not np.all(active_columns):
    return _compact(gram, rhs, precision, covariance, active_columns)''').body[0]
    posterior.body.insert(root_index, fast)
    index = function.body.index(posterior)
    function.body.insert(index, ast.parse('active_columns = np.any(u != 0, axis=0)').body[0])
    tree = ast.fix_missing_locations(tree)
    scope = dict(vars(hierarchical), _compact=compact)
    exec(compile(tree, '<inactive-posterior-columns>', 'exec'), scope)
    return scope['hierarchical_bound'], source, ast.unparse(tree)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.resolve().is_relative_to('/mnt/qnap01'):
        p.error('QNAP is read-only')
    args.output.mkdir(exist_ok=False)
    meta, raw = args.capture/'hardest.json', args.capture/'hardest.npz'
    metadata = json.loads(meta.read_bytes())
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == metadata['arrays_sha256']
    with np.load(raw, allow_pickle=False) as data:
        positional = [data[f'argument_{i}'] for i in range(4)]
        keywords = dict(metadata['scalar_keywords'])
        keywords.update({k.removeprefix('keyword_'):data[k] for k in data.files
                         if k.startswith('keyword_')})
    function, original, generated = candidate()
    paths = [Path(__file__), Path(hierarchical.__file__), meta, raw,
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(q.resolve()):hashlib.sha256(q.read_bytes()).hexdigest() for q in paths}
    before = fingerprint((positional, keywords))
    baseline = hierarchical.hierarchical_bound(*positional, **keywords)
    proposed = function(*positional, **keywords)
    differences = [k for k in baseline if fingerprint(baseline[k])!=fingerprint(proposed[k])]
    report = dict(exact=not differences, differing_fields=differences, bindings=bindings,
                  baseline=fingerprint(baseline), candidate=fingerprint(proposed),
                  coefficient_max_abs_difference=float(np.max(abs(
                      baseline['coefficient']-proposed['coefficient']), initial=0)),
                  inactive_columns=np.flatnonzero(~np.any(positional[1]!=0,axis=0)).tolist(),
                  baseline_iterations=baseline['precision_iterations'],
                  candidate_iterations=proposed['precision_iterations'],
                  unchanged_inputs=before==fingerprint((positional,keywords)),
                  inference_modified=False, full_pipeline_speedup=None)
    assert report['unchanged_inputs']
    assert all(hashlib.sha256(Path(q).read_bytes()).hexdigest()==h for q,h in bindings.items())
    (args.output/'original.py').write_text(original.rstrip()+'\n')
    (args.output/'generated.py').write_text(generated.rstrip()+'\n')
    (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in
                     ('baseline','candidate','bindings')}))


if __name__ == '__main__':
    main()
