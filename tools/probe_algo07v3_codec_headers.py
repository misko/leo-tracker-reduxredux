"""Profile and benchmark complete archive encoding on fresh live pipeline evidence.

No reloaded arrays are used as a surrogate for the live object graph. The
external candidate reuses only emitted NPY headers, never array data or hashes.
"""

import argparse
import hashlib
import inspect
import io
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from profile_algo07v3 import resources, timed

from leo.cli.algo07v3 import supervise, worker, write
from leo.storage import localization_v3 as storage
from leo.storage import localization_v3_codec as codec


def array_bytes(a, headers):
    key = None
    if (a.dtype.fields is None and a.dtype.subdtype is None and a.dtype.metadata is None
            and not a.dtype.hasobject and (a.flags.c_contiguous or a.flags.f_contiguous)):
        fortran = bool(a.flags.f_contiguous and not a.flags.c_contiguous)
        key = (a.dtype.str, a.shape, fortran)
        if key in headers:
            return headers[key] + a.tobytes(order='F' if fortran else 'C')
    stream = io.BytesIO()
    np.save(stream, a, allow_pickle=False)
    raw = stream.getvalue()
    if key is not None:
        headers[key] = raw[:len(raw) - a.nbytes]
    return raw


def transform():
    original = inspect.getsource(codec.pack)
    old = ('            stream = io.BytesIO()\n'
           '            np.save(stream, a, allow_pickle=False)\n'
           '            raw = stream.getvalue()')
    if original.count(old) != 1 or original.count('    blobs = {}') != 1:
        raise ValueError('Review pack boundaries before transforming')
    changed = original.replace('    blobs = {}', '    blobs = {}\n    headers = {}').replace(
        old, '            raw = _array_bytes(a, headers)')
    scope = dict(vars(codec), _array_bytes=array_bytes)
    exec(compile(changed, '<cached-npy-headers>', 'exec'), scope)
    return scope['pack'], original, changed


def profiled_pack(value, pngs):
    clocks, counts, identities, shapes = defaultdict(float), Counter(), {}, Counter()

    def observe(name, function):
        def call(*args, **kwargs):
            began = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                clocks[name] += time.perf_counter() - began
                counts[name] += 1
        return call

    class Numpy:
        def __getattr__(self, name):
            return getattr(np, name)

        def save(self, stream, a, **kwargs):
            identities[id(a)] = a  # Keep references so temporary IDs cannot be reused.
            shapes[(a.dtype.str, a.shape, bool(a.flags.f_contiguous and
                                             not a.flags.c_contiguous))] += 1
            counts['array_bytes'] += a.nbytes
            return observe('numpy_save', np.save)(stream, a, **kwargs)

    class Archive(codec.zipfile.ZipFile):
        def writestr(self, name, data, **kwargs):
            kind = 'zip_header' if name.filename == 'values.json' else 'zip_blobs'
            return observe(kind, super().writestr)(name, data, **kwargs)

    class Zip:
        ZipFile = Archive

        def __getattr__(self, name):
            return getattr(codec.zipfile, name)

    scope = dict(vars(codec), np=Numpy(), zipfile=Zip(),
                 canonical_json_bytes=observe('json_header', codec.canonical_json_bytes),
                 sha256_digest=observe('hash', codec.sha256_digest))
    exec(compile(inspect.getsource(codec.pack), '<profile-archive-pack>', 'exec'), scope)
    began = time.perf_counter()
    raw = scope['pack'](value, pngs)
    total = time.perf_counter() - began
    return raw, dict(seconds=total, clocks=dict(clocks), counts=dict(counts),
                     remaining_seconds=total - sum(clocks.values()),
                     unique_array_objects=len(identities), distinct_shape_keys=len(shapes),
                     repeated_shape_calls=sum(n - 1 for n in shapes.values()))


def observed_worker(root):
    original = storage.pack
    candidate, _, _ = transform()
    calls = []

    def measured(value, pngs):
        rows = []
        expected = timed(lambda: original(value, pngs), rows, 'original_first')
        profiled, profile = profiled_pack(value, pngs)
        if profiled != expected:
            raise ValueError('Profile instrumentation changed archive bytes')
        del profiled
        for pair in range(3):
            order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
            for side in order:
                operation = original if side == 'baseline' else candidate
                raw = timed(lambda operation=operation: operation(value, pngs), rows, side)
                rows[-1].update(pair=pair, exact=raw == expected)
                if raw != expected:
                    raise ValueError('Complete archive bytes differ')
                del raw
        calls.append(dict(profile=profile, rows=rows, archive_bytes=len(expected),
                          archive_sha256=hashlib.sha256(expected).hexdigest()))
        write(root / 'encoding.json', calls)
        print(json.dumps(dict(event='encoding_complete', call=len(calls), exact=True,
                              profile=profile)), flush=True)
        return expected

    storage.pack = measured
    try:
        return worker(root / 'request.json', root / 'worker.json', False)
    finally:
        storage.pack = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path)
    args = parser.parse_args()
    if args.worker:
        return observed_worker(args.worker)
    if not args.request or not args.output:
        parser.error('--request and --output required')
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 3:
        parser.error('Pin three CPUs and one BLAS thread')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    root.mkdir(exist_ok=False)
    request = json.loads(args.request.read_bytes())
    write(root / 'request.json', dict(request, output_root=str(root / 'publication')))
    _, original, changed = transform()
    (root / 'original-pack.py').write_text(original)
    (root / 'candidate-pack.py').write_text(changed)
    paths = [*Path('src').rglob('*.py'), Path(__file__), args.request, root / 'request.json',
             Path('tools/profile_algo07v3.py'), root / 'original-pack.py',
             root / 'candidate-pack.py']
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    write(root / 'plan.json', dict(bindings=bindings, cpus=sorted(os.sched_getaffinity(0)),
                                   blas_threads=1, timeout_seconds=1200,
                                   runtime_integrated=False, production_modified=False))
    write(root / 'resources-start.json', resources())
    with (root / 'worker.log').open('xb') as log:
        outcome = supervise([sys.executable, '-B', str(Path(__file__).resolve()),
                             '--worker', str(root)], log=log, timeout=1200,
                            environment=dict(os.environ))
    changed = [p for p, sha in bindings.items()
               if hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha]
    result_path = root / 'worker.json'
    result = json.loads(result_path.read_bytes()) if result_path.exists() else None
    write(root / 'resources-end.json', resources())
    write(root / 'benchmark.json', dict(process=outcome, worker=result, changed_sources=changed,
                                       full_pipeline_speed_benchmark=False))
    return 0 if outcome['returncode'] == 0 and result and not changed else 1


if __name__ == '__main__':
    raise SystemExit(main())
