"""Bounded-cohort track extraction oracle runner; never used by v3 inference.

Invoke each side in its own pinned Python environment. The input plan contains
only native GLRT bytes/configuration; reference outputs never enter the candidate.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    import numpy as np

    def default(item):
        if isinstance(item, np.ndarray):
            return item.tolist()
        if isinstance(item, np.generic):
            return item.item()
        raise TypeError(type(item).__name__)

    with Path(path).open('x') as stream:
        json.dump(value, stream, allow_nan=False, sort_keys=True, default=default)
        stream.write('\n')


def deny_legacy(event, args):
    """Candidate process guard in addition to the deliberately narrow PYTHONPATH."""
    if event in ('subprocess.Popen', 'os.system', 'os.posix_spawn'):
        raise RuntimeError('Track preparation may not launch a worker')
    if event == 'import':
        name = args[0]
        if name.startswith(('algo0', 'evaluate_ds', 'leo.storage', 'leo.operations')):
            raise RuntimeError('Historical worker/storage dependency: ' + name)
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = Path(args[0].decode() if isinstance(args[0], bytes) else args[0]).resolve()
        if path.is_relative_to('/opt/leo') or str(path).startswith('/opt/leo-'):
            raise RuntimeError('Candidate attempted historical runtime read')


def run(args):
    plan_bytes = args.plan.read_bytes()
    plan = json.loads(plan_bytes)
    if plan['kind'] != 'algo07v3-track-preparation-cohort':
        raise ValueError('Declared native-only track cohort required')
    if args.side == 'candidate':
        sys.addaudithook(deny_legacy)
        from leo.analysis.localization_v3.tracks import prepare_tracks
    else:
        # Reference-only imports. This branch is excluded from the v3 package.
        from evaluate_ds22_merged_tracks import winners
        from evaluate_ds22_public_tracks import graph_rf_lanes
        from localize_merged_track_catalogue import raw_curvature

        def prepare_tracks(document, config):
            rows, metadata = winners(document)
            tracks, count = graph_rf_lanes(rows, 'SCAN', config)
            curved = [i for i, track in enumerate(tracks) if raw_curvature(track)]
            return dict(observations=rows, metadata=metadata, tracks=tracks,
                        graph_points=count, curved_indices=curved,
                        status='tracks_prepared' if curved else 'no_active_curvature')

    from leo.analysis.polynomial_tracklets import TrackConfig

    config = TrackConfig(**plan['config'])
    pins = plan['source_pins'][args.side]
    if any(digest(path) != sha for path, sha in pins.items()):
        raise ValueError('Prepared source pins changed')
    args.output.mkdir(exist_ok=False)
    results = []
    started = time.monotonic()
    for member in plan['members']:
        label = member['dataset_label']
        row = dict(dataset_label=label, availability=member['availability'])
        if member['availability'] != 'available':
            row['state'] = 'unavailable'
        else:
            try:
                payload = Path(member['native_path']).read_bytes()
                if 'sha256:' + hashlib.sha256(payload).hexdigest() != member['input_sha256']:
                    raise ValueError('Native input differs from frozen DS26 inventory')
                began = time.monotonic()
                result = prepare_tracks(json.loads(payload), config)
                row['seconds'] = time.monotonic() - began
                target = args.output / (label + '.json')
                write(target, result)
                row.update(state='complete', output_sha256=digest(target),
                           points=len(result['observations']), tracks=len(result['tracks']),
                           assigned=result['graph_points'], curved=len(result['curved_indices']))
            except Exception as error:
                row.update(state='failed', error=f'{type(error).__name__}: {error}')
        results.append(row)
        write(args.output / (label + '-receipt.json'), row)
        print(json.dumps(row), flush=True)
    intact = (args.plan.read_bytes() == plan_bytes
              and all(digest(path) == sha for path, sha in pins.items()))
    modules = {name: str(Path(module.__file__).resolve())
               for name, module in sys.modules.items()
               if name.startswith('leo.') and getattr(module, '__file__', None)}
    summary = dict(side=args.side, modules=modules, rows=results, pins_intact=intact,
                   plan_sha256=hashlib.sha256(plan_bytes).hexdigest(),
                   wall_seconds=time.monotonic() - started,
                   full_localization_parity=False, speedup_established=False)
    write(args.output / 'summary.json', summary)
    return int(not intact or any(row['state'] == 'failed' for row in results))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--side', choices=('reference', 'candidate'), required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(run(parser.parse_args()))
