"""Observe a captured precision trajectory and detect exact repeated loop states."""

import argparse
import hashlib
import inspect
import json
import os
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import hierarchical


def observed(record):
    source = inspect.getsource(hierarchical.hierarchical_bound)
    needle = '        rate, prior_rate = next_rate, next_prior_rate'
    if source.count(needle) != 1:
        raise ValueError('Review changed precision-update boundary')
    inserted = ('        _record(rate, prior_rate, next_rate, next_prior_rate, change)\n'
                + needle)
    scope = dict(vars(hierarchical), _record=record)
    exec(compile(source.replace(needle, inserted), '<precision-observer>', 'exec'), scope)
    return scope['hierarchical_bound']


class Trajectory:
    def __init__(self):
        self.rows, self.states = [], {}

    def record(self, rate, prior_rate, next_rate, next_prior_rate, change):
        # These are the complete changing inputs to the next deterministic
        # posterior iteration. Byte keys distinguish exact from approximate cycles.
        key = (rate.tobytes(), prior_rate.tobytes())
        previous = self.states.get(key)
        self.states.setdefault(key, len(self.rows))
        noise_change = np.log(next_rate/rate)
        prior_change = np.log(next_prior_rate/prior_rate)
        self.rows.append(dict(
            index=len(self.rows), repeated_state_from=previous,
            change=float(change), noise_log_change=noise_change.tolist(),
            prior_log_change=prior_change.tolist(), rate=rate.tolist(),
            prior_rate=prior_rate.tolist(), next_rate=next_rate.tolist(),
            next_prior_rate=next_prior_rate.tolist()))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        p.error('One CPU and one BLAS thread required')
    if args.output.resolve().is_relative_to('/mnt/qnap01'):
        p.error('QNAP is read-only')
    args.output.mkdir(exist_ok=False)
    meta, arrays = args.capture/'hardest.json', args.capture/'hardest.npz'
    metadata = json.loads(meta.read_bytes())
    assert hashlib.sha256(arrays.read_bytes()).hexdigest() == metadata['arrays_sha256']
    with np.load(arrays, allow_pickle=False) as saved:
        positional = [saved[f'argument_{i}'] for i in range(4)]
        keywords = dict(metadata['scalar_keywords'])
        keywords.update({k.removeprefix('keyword_'): saved[k] for k in saved.files
                         if k.startswith('keyword_')})
    paths = [meta, arrays, Path(__file__), Path(hierarchical.__file__),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(q.resolve()): hashlib.sha256(q.read_bytes()).hexdigest() for q in paths}
    before = fingerprint((positional, keywords))
    expected = hierarchical.hierarchical_bound(*positional, **keywords)
    trajectory = Trajectory()
    actual = observed(trajectory.record)(*positional, **keywords)
    exact = fingerprint(expected) == fingerprint(actual)
    unchanged = before == fingerprint((positional, keywords))
    result = dict(exact=exact, unchanged_inputs=unchanged, bindings=bindings,
                  iterations=len(trajectory.rows),
                  repeated_states=sum(r['repeated_state_from'] is not None
                                      for r in trajectory.rows),
                  final_change=actual['final_log_precision_change'], rows=trajectory.rows,
                  profiler_only=True, measured_speedup=None)
    (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    assert exact and unchanged and len(trajectory.rows) == actual['precision_iterations']
    assert all(hashlib.sha256(Path(q).read_bytes()).hexdigest() == digest
               for q, digest in bindings.items())
    print(json.dumps({k: result[k] for k in ('exact', 'iterations', 'repeated_states',
                                          'final_change')}), flush=True)


if __name__ == '__main__':
    main()
