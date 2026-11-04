"""Real-bank primitive benchmark, not a pipeline speed or cache-hit-rate claim."""
import argparse
import hashlib
import json
import time
from dataclasses import fields
from pathlib import Path

import numpy as np

from leo.analysis.localization_v3.geometry import ScanGeometry
from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_digest(result):
    hashes = {}
    for field in fields(result):
        value = getattr(result, field.name)
        if isinstance(value, np.ndarray):
            hashes[field.name] = dict(dtype=value.dtype.str, shape=list(value.shape),
                                     sha256=hashlib.sha256(value.tobytes()).hexdigest())
        else:
            hashes[field.name] = array_digest(value)
    return hashes


def main(args):
    descriptor = args.export / 'descriptor.json'
    document = json.loads(descriptor.read_bytes())
    names = ['worker/inference/SCAN/bank.npz', 'worker/inference/SCAN/tracks.json']
    pins = {name: document['files'][name] for name in names}
    for name, expected in pins.items():
        if 'sha256:' + sha(args.export / name) != expected:
            raise ValueError('Changed public worker-evidence export')
    with np.load(args.export / names[0]) as data:
        bank = dict(data)
    tracks = json.loads((args.export / names[1]).read_bytes())
    times = np.unique(np.concatenate([t['times'] for t in tracks]))
    plan = dict(scope='Three identical full-bank phase preparation queries, primitive only',
                source_descriptor=str(descriptor), source_descriptor_sha256=sha(descriptor),
                source_files=pins, repeats=3, maximum_cache_bytes=1024*1024*1024,
                points=len(times), satellites=len(bank['norad']), phases=0.,
                ordering=['reference', 'candidate', 'candidate', 'reference'],
                baseline_complete_path_seconds=None, candidate_complete_path_seconds=None,
                pipeline_speedup_established=False, representative_hit_rate_measured=False)
    args.output.mkdir(exist_ok=False)
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    trials = []
    expected = None
    for side in plan['ordering']:
        began = time.monotonic()
        context = ScanGeometry(bank, maximum_cache_bytes=plan['maximum_cache_bytes']) \
            if side == 'candidate' else None
        setup = time.monotonic() - began
        durations = []
        for _ in range(3):
            start = time.monotonic()
            value = context.prepare(times) if context else prepare_phase_geometry(bank, times)
            durations.append(time.monotonic()-start)
            fingerprint = array_digest(value)
            if expected is None:
                expected = fingerprint
            if fingerprint != expected:
                raise ValueError('Exact geometry comparison failed')
            del value
        trials.append(dict(side=side, setup_seconds=setup, query_seconds=durations,
                           counted_seconds=setup+sum(durations),
                           hits=context.hits if context else 0,
                           misses=context.misses if context else 3,
                           cached_bytes=context.cached_bytes if context else 0))
        del context
    if any('sha256:' + sha(args.export / name) != expected for name, expected in pins.items()):
        raise ValueError('Source changed during trial')
    result = dict(plan=plan, trials=trials, exact_geometry=True, fingerprint=expected,
                  observed_wall_seconds_excludes_hashing=False,
                  counted_seconds_excludes_hashing=True,
                  full_localization_parity=False, pipeline_speedup_established=False)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(trials=trials, exact_geometry=True)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
