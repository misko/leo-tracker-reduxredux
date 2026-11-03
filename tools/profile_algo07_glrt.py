"""Freeze small native-window fixtures and profile ALGO07's production GLRT stage."""

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'runtime_profile_cli', ROOT/'src/leo/cli/algo07_profile.py')
PROFILE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROFILE)


def use_source(root):
    """Never silently benchmark the older repository GLRT against native data."""
    source = root.resolve(strict=True)/'src'
    if 'leo' in sys.modules:
        raise RuntimeError('Choose the native source before importing leo')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source))
    return source


def select_visits(probes, *, per_channel=2, seed=20261103):
    import numpy as np

    if type(per_channel) is not int or not 1 <= per_channel <= 4:
        raise ValueError('one to four windows per channel required')
    by_channel = {}
    labels = {}
    for row in probes:
        visit, channel = row['visit_index'], row['channel']
        if visit in labels and labels[visit] != channel:
            raise ValueError('conflicting channel for one visit')
        labels[visit] = channel
        by_channel.setdefault(channel, set()).add(visit)
    if set(by_channel) != set(range(1, 9)):
        raise ValueError('all eight native channels required')
    rng = np.random.default_rng(seed)
    return sorted(int(i) for ch in sorted(by_channel) for i in rng.choice(
        sorted(by_channel[ch]), size=per_channel, replace=False))


def locate(inventory, visit):
    start = 0
    for entry in inventory['segments']:
        if start <= visit < start+entry['windows']:
            return entry, visit-start
        start += entry['windows']
    raise ValueError('visit outside the sealed source inventory')


def snapshot(args):
    source = use_source(args.source_root)
    import numpy as np

    from leo.storage.fast_scan import FastScanStore, FastSegmentSource

    store = FastScanStore(args.bulk_root)
    report = store.detail(args.run_id, include_points=False)
    tracking_path = store.tracking_input_path(args.run_id)
    tracking_sha = PROFILE.digest(tracking_path)
    tracking = json.loads(tracking_path.read_text())
    inventory = store.source(report['session_id'], tracking['source']['input_manifest_sha256'])
    probes = tracking['source']['probes']
    visits = select_visits(probes, per_channel=args.per_channel, seed=args.seed)
    output = PROFILE.destination(args.output)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for visit in visits:
        entry, sequence = locate(inventory, visit)
        reader = FastSegmentSource(entry, start_sequence=sequence, stop_sequence=sequence+1)
        # Exhaust the iterator so the reader also verifies complete chunk hashes.
        windows = list(reader.windows())
        if len(windows) != 1 or windows[0].acquisition['global_visit'] != visit:
            raise ValueError('native visit/segment sequence differs')
        window = windows[0]
        name = f'visit-{visit:06d}.npy'
        np.save(output/name, window.samples, allow_pickle=False)
        rows.append(dict(visit=visit, sequence=window.sequence, iq_sha256=window.iq_sha256,
                         acquisition=window.acquisition, target=window.target,
                         sample_rate_hz=window.sample_rate_hz, receiver_ids=reader.receiver_ids,
                         samples=name, source_entry=entry,
                         expected_probes=[p for p in probes if p['visit_index'] == visit]))
    if PROFILE.digest(tracking_path) != tracking_sha or inventory != store.source(
            report['session_id'], tracking['source']['input_manifest_sha256']):
        raise ValueError('source evidence changed during fixture export')
    PROFILE.write_new(output/'input.json', dict(
        run_id=args.run_id, recording=report['recording_name'], source_root=str(args.source_root),
        tracking_sha256=tracking_sha, policy=report['policy'], windows=rows,
        selection=dict(seed=args.seed, per_channel=args.per_channel,
                       unit='whole paired-receiver window, sampled within each channel'),
        scope='Bounded GLRT kernel fixture; not a full scan or localization replay'))
    files = [dict(path=str(p), sha256=PROFILE.digest(p)) for p in output.iterdir()]
    code = sorted(source.rglob('*.py')) + sorted(args.source_root.rglob('*.so'))
    files += [dict(path=str(p), sha256=PROFILE.digest(p)) for p in code]
    PROFILE.write_new(output/'spec.json', dict(files=files))
    frozen = PROFILE.freeze(output/'spec.json', output/'frozen.json')
    print(json.dumps(dict(windows=len(rows), frozen_files=len(frozen['files']),
                          sample_rates=sorted({r['sample_rate_hz'] for r in rows}))))


def published_candidates(receiver):
    fields = ('candidate_rank', 'fractional_epoch_offset_samples',
              'fractional_tracking_cfo_hz', 'fractional_exact_score',
              'fractional_control_score', 'fractional_margin')
    result = []
    for candidate in receiver.candidates:
        if candidate.fractional_epoch_status != 'complete' or any(
                getattr(candidate, name) is None for name in fields):
            continue
        result.append(dict(
            {name: getattr(candidate, name) for name in fields},
            integer_epoch_sample=candidate.epoch_sample,
            passed_fractional_margin_gate=candidate.fractional_margin >= .025))
    return result


def execute(args):
    use_source(args.source_root)
    import numpy as np

    from leo.scanner.fast_scan_analysis import VerifiedFastWindow, production_glrt

    document = json.loads(args.input.read_text())
    rows = []
    for item in document['windows']:
        window = VerifiedFastWindow(
            item['sequence'], item['iq_sha256'], item['acquisition'], item['target'],
            np.load(args.input.parent/item['samples'], allow_pickle=False), item['sample_rate_hz'])
        began = time.perf_counter()
        receivers = production_glrt(window, tuple(item['receiver_ids']))
        seconds = time.perf_counter()-began
        expected = {p['receiver_id']: p['candidates'] for p in item['expected_probes']}
        exact = all(published_candidates(r) == expected[r.receiver_id] for r in receivers)
        rows.append(dict(visit=item['visit'], channel=item['target']['channel'], seconds=seconds,
                         published_candidates_exact=exact,
                         receivers=[r.model_dump(mode='json') for r in receivers]))
        print(json.dumps(dict(visit=item['visit'], seconds=seconds, exact=exact)), flush=True)
    PROFILE.write_new(args.output, dict(
        windows=rows, published_candidates_exact=all(r['published_candidates_exact'] for r in rows),
        total_detector_seconds=sum(r['seconds'] for r in rows), full_scan_replayed=False,
        source_root=str(args.source_root.resolve()), window_count=len(rows)))
    if not all(r['published_candidates_exact'] for r in rows):
        raise SystemExit('Native GLRT differs from the published candidate evidence')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('snapshot')
    p.add_argument('--bulk-root', type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--per-channel', type=int, default=2)
    p.add_argument('--seed', type=int, default=20261103)
    p = commands.add_parser('run')
    p.add_argument('--snapshot', type=Path, required=True)
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--timeout', type=float, default=300)
    p.add_argument('--no-cprofile', action='store_true')
    p = commands.add_parser('execute')
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'snapshot':
        snapshot(args)
    elif args.command == 'execute':
        execute(args)
    else:
        root = args.snapshot.resolve(strict=True)
        output = PROFILE.destination(args.output)
        if not output.is_relative_to(root) or output == root:
            raise ValueError('new trial output must be inside its isolated snapshot')
        os.environ.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        result = PROFILE.run(argparse.Namespace(
            manifest=root/'frozen.json', output=output, script=Path(__file__),
            stage='native-fast-glrt', timeout=args.timeout, no_cprofile=args.no_cprofile,
            arguments=['execute', '--input', str(root/'input.json'), '--output',
                       str(output/'result.json'), '--source-root', str(args.source_root)]))
        print(json.dumps(result))
        if not result['successful_execution']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
