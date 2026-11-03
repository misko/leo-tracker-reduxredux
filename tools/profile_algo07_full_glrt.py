"""Bounded full-scan native GLRT replay through public recording ports."""

import argparse
import json
import multiprocessing
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import profile_algo07_glrt as fixture

PROFILE = fixture.PROFILE


def spans(inventory, width=64):
    offset = 0
    for entry in inventory['segments']:
        for start in range(0, entry['windows'], width):
            stop = min(start+width, entry['windows'])
            yield dict(entry=entry, start=start, stop=stop, offset=offset)
        offset += entry['windows']


def compare_receivers(receivers, expected):
    actual = {r.receiver_id: fixture.published_candidates(r) for r in receivers}
    reference = {r['receiver_id']: r['candidates'] for r in expected}
    if len(reference) != len(expected):
        raise ValueError('duplicate receiver in reference')
    return actual == reference


def initialize(source):
    fixture.use_source(Path(source))


def replay(task, policy_document, expected, destination):
    from leo.contracts.fast_scan_native import parse_fast_policy
    from leo.scanner.fast_scan_analysis import analyze_window
    from leo.storage.fast_scan import FastSegmentSource

    reader = FastSegmentSource(task['entry'], start_sequence=task['start'],
                               stop_sequence=task['stop'])
    policy = parse_fast_policy(policy_document)
    rows = []
    for index, window in enumerate(reader.windows(), start=task['start']):
        visit = task['offset']+index
        if window.acquisition['global_visit'] != visit:
            raise ValueError('recording visit differs from inventory')
        began, cpu = time.perf_counter(), time.process_time()
        result = analyze_window(window, reader.receiver_ids, None, policy)
        seconds, cpu_seconds = time.perf_counter()-began, time.process_time()-cpu
        references = expected.get(visit, [])
        exact = compare_receivers(result.receivers, references)
        if result.status == 'processed' and not references:
            exact = False
        if result.status != 'processed' and references:
            exact = False
        # Preserve all receiver candidates, including unpublished hypotheses.
        rows.append(dict(visit=visit, seconds=seconds, cpu_seconds=cpu_seconds,
                         published_candidates_exact=exact,
                         result=result.model_dump(mode='json')))
    # Iterator exhaustion above is required for complete compressed-chunk checks.
    if len(rows) != task['stop']-task['start']:
        raise ValueError('missing source windows')
    name = f"visits-{task['offset']+task['start']:06d}.json"
    PROFILE.write_new(Path(destination)/name, dict(task=task, windows=rows))
    return dict(path=name, windows=len(rows),
                exact=all(r['published_candidates_exact'] for r in rows),
                processed=sum(r['result']['status'] == 'processed' for r in rows),
                detector_seconds=sum(r['seconds'] for r in rows),
                detector_cpu_seconds=sum(r['cpu_seconds'] for r in rows))


def snapshot(args):
    fixture.use_source(args.source_root)
    from leo.storage.fast_scan import FastScanStore

    store = FastScanStore(args.bulk_root)
    report = store.detail(args.run_id, include_points=False)
    policy = report['policy']
    if policy['schema_version'] != 2 or policy['mode'] != 'ungated':
        raise ValueError('full replay currently requires ungated native policy v2')
    tracking_path = store.tracking_input_path(args.run_id)
    tracking_hash = PROFILE.digest(tracking_path)
    tracking = json.loads(tracking_path.read_text())
    inventory = store.source(report['session_id'], tracking['source']['input_manifest_sha256'])
    output = PROFILE.destination(args.output)
    output.mkdir(parents=True, exist_ok=False)
    PROFILE.write_new(output/'input.json', dict(run_id=args.run_id, report=report,
                      inventory=inventory, expected_probes=tracking['source']['probes']))
    files = [dict(path=str(output/'input.json')),
             dict(path=str(tracking_path), sha256=tracking_hash)]
    for root in (args.source_root, args.candidate_root):
        files += [dict(path=str(p)) for p in sorted((root/'src').rglob('*'))
                  if p.is_file() and p.suffix in ('.py', '.so')]
    PROFILE.write_new(output/'spec.json', dict(files=files))
    PROFILE.freeze(output/'spec.json', output/'frozen.json')
    print(json.dumps(dict(windows=sum(e['windows'] for e in inventory['segments']),
                          expected_probes=len(tracking['source']['probes']))))


def execute(args):
    document = json.loads(args.input.read_text())
    probes = {}
    for row in document['expected_probes']:
        probes.setdefault(row['visit_index'], []).append(row)
    began = time.perf_counter()
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers,
                             mp_context=multiprocessing.get_context('spawn'),
                             initializer=initialize, initargs=(str(args.source_root),)) as pool:
        futures = []
        for task in spans(document['inventory']):
            first, last = task['offset']+task['start'], task['offset']+task['stop']
            expected = {visit: probes[visit] for visit in range(first, last) if visit in probes}
            futures.append(pool.submit(replay, task, document['report']['policy'], expected,
                                       str(args.output/'windows')))
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            print(json.dumps(dict(completed_ranges=len(rows), **row)), flush=True)
    total = sum(e['windows'] for e in document['inventory']['segments'])
    result = dict(windows=sum(r['windows'] for r in rows), expected_windows=total,
                  processed=sum(r['processed'] for r in rows),
                  expected_processed=len(probes), workers=args.workers,
                  wall_seconds=time.perf_counter()-began,
                  detector_cpu_seconds=sum(r['detector_cpu_seconds'] for r in rows),
                  exact=all(r['exact'] for r in rows), ranges=sorted(rows,key=lambda r:r['path']),
                  localization_replayed=False, production_modified=False)
    assert result['windows'] == total and result['processed'] == len(probes)
    PROFILE.write_new(args.output/'result.json', result)
    if not result['exact']:
        raise SystemExit('Published GLRT candidate mismatch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('snapshot')
    p.add_argument('--bulk-root', type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--candidate-root', type=Path, required=True)
    for name in ('run', 'execute'):
        p = sub.add_parser(name)
        p.add_argument('--workers', type=int, choices=range(1, 17), default=8)
        if name == 'run':
            p.add_argument('--snapshot', type=Path, required=True)
            p.add_argument('--timeout', type=float, default=1800)
        else:
            p.add_argument('--input', type=Path, required=True)
    for p in sub.choices.values():
        p.add_argument('--source-root', type=Path, required=True)
        p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'snapshot':
        snapshot(args)
    elif args.command == 'execute':
        execute(args)
    else:
        root = args.snapshot.resolve(strict=True)
        output = PROFILE.destination(args.output)
        if not output.is_relative_to(root) or output == root:
            raise ValueError('trial must be a new directory inside its snapshot')
        os.environ.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        result = PROFILE.run(argparse.Namespace(
            manifest=root/'frozen.json', output=output, script=Path(__file__),
            stage='full-native-glrt', timeout=args.timeout, no_cprofile=True,
            arguments=['execute', '--input', str(root/'input.json'), '--output', str(output),
                       '--source-root', str(args.source_root), '--workers', str(args.workers)]))
        print(json.dumps(result))
        if not result['successful_execution']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
