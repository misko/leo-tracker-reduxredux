"""Checkpoint orbit-blind refinement by visit; bounded offline pilot or full scan."""
import argparse
import inspect
import json
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from cohort import canonical, digest
from refinement import refine, winners
from iq_visits import read_event, visit_ordinals


def worker(task):
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
    import numpy as np
    signature, visit_index, rows = task
    store = AdaptiveHopIqStore(Path('/srv/bulk/leo'), read_only=True)
    try:
        published = store.inspect(signature['session_id'])
        if published.manifest_sha256 != signature['manifest_sha256']:
            raise ValueError('IQ capture changed')
        fs = int(published.manifest.receipt.plan.geometry.sample_rate_hz)
        if visit_index not in visit_ordinals(published.manifest.receipt):
            return dict(signature=signature, visit_index=visit_index, records=[dict(
                row_index=row['row_index'], candidate_id=row['candidate_id'], probe_key=row['probe_key'],
                original_hz=row['original_hz'], original_margin=row['original_margin'],
                output_hz=row['original_hz'], refinement_seconds=0.,
                refinement=dict(status='iq_not_retained', calls=0, trace=[])) for row in rows])
        visit, iq = read_event(store, published, visit_index)
        signals, results = {}, []
        for row in rows:
            key = (row['receiver'], row['probe_start_ms'])
            if key not in signals:
                begin = row['probe_start_ms'] * fs // 1000
                block = iq[begin:begin + fs//50, row['receiver'], :]
                if len(block) != fs//50:
                    raise ValueError('20 ms probe extends outside the stored visit')
                signals[key] = (block[:, 0].astype(float) + 1j*block[:, 1].astype(float))/32768.

            def score(frequency, epoch):
                integer = int(round(epoch))
                value = conditioned_glrt64_score(signals[key], fs, epoch_sample=integer,
                    fractional_epoch_offset_samples=epoch-integer, acquired_cfo_hz=float(frequency),
                    edge=visit.event.target.edge, glrt_size=4096)
                return dict(tracking_cfo_hz=value.tracking_cfo_hz, margin=value.margin,
                            exact=value.exact_score, control=value.control_score)

            start = time.monotonic()
            fit = refine(score, row['original_hz'], row['integer_epoch_sample'] + row['fractional_epoch_offset_samples'])
            result = dict(row_index=row['row_index'], candidate_id=row['candidate_id'],
                          probe_key=row['probe_key'], original_hz=row['original_hz'],
                          original_margin=row['original_margin'], refinement=fit,
                          output_hz=fit['tracking_cfo_hz'] if fit['status'] == 'refined' else row['original_hz'],
                          refinement_seconds=time.monotonic()-start)
            results.append(result)
        return dict(signature=signature, visit_index=visit_index, records=results)
    finally:
        store.close()


def main():
    from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observations', type=Path)
    parser.add_argument('--workers', type=int, default=2, choices=(1, 2))
    parser.add_argument('--maximum-new-visits', type=int)
    args = parser.parse_args()
    if args.maximum_new_visits is not None and args.maximum_new_visits < 1:
        raise ValueError('maximum-new-visits must be positive')
    input_raw = args.observations.read_bytes()
    data = json.loads(input_raw)
    directory = args.observations.parent/'refinement'
    directory.mkdir(exist_ok=True)
    sources = [Path(__file__), Path(inspect.getfile(refine)),
               Path(inspect.getfile(conditioned_glrt64_score)), Path(inspect.getfile(AdaptiveHopIqStore)),
               Path(inspect.getfile(read_event))]
    signature = dict(observations_sha256=digest(input_raw), session_id=data['summary']['session_id'],
                     manifest_sha256=data['signature']['manifest_sha256'],
                     sources={str(p): digest(p.read_bytes()) for p in sources})
    grouped = defaultdict(list)
    for row in data['records']:
        grouped[row['probe_key'][0]].append(row)
    completed, tasks = [], []
    for visit, rows in sorted(grouped.items()):
        output = directory/f'visit-{visit:05d}.json'
        if output.exists():
            checkpoint = json.loads(output.read_text())
            if checkpoint['signature'] != signature or checkpoint['visit_index'] != visit:
                raise ValueError('refinement resume input/source mismatch')
            if {r['row_index'] for r in checkpoint['records']} != {r['row_index'] for r in rows}:
                raise ValueError('refinement checkpoint row mismatch')
            completed.extend(checkpoint['records'])
        else:
            tasks.append((signature, visit, rows))
    if args.maximum_new_visits:
        tasks = tasks[:args.maximum_new_visits]
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        pending = {pool.submit(worker, task): directory/f'visit-{task[1]:05d}.json' for task in tasks}
        for index, future in enumerate(as_completed(pending), 1):
            checkpoint = future.result()
            canonical(checkpoint)
            with pending[future].open('x') as stream:
                json.dump(checkpoint, stream, allow_nan=False)
            completed.extend(checkpoint['records'])
            if index % 10 == 0:
                print(json.dumps(dict(new_visits=index, candidates=len(completed), elapsed_s=time.monotonic()-started)), flush=True)
    finished = len(completed) == len(data['records'])
    if len({r['row_index'] for r in completed}) != len(completed):
        raise ValueError('duplicate refinement output')
    summary = dict(status='complete' if finished else 'partial', signature=signature,
                   completed_candidates=len(completed), total_candidates=len(data['records']),
                   failed_refinements=sum(r['refinement']['status'] != 'refined' for r in completed),
                   completed_windows=len(winners(completed)), new_visits=len(tasks),
                   invocation_elapsed_s=time.monotonic()-started,
                   cumulative_candidate_compute_s=sum(r['refinement_seconds'] for r in completed))
    # Generated progress snapshots are replaceable; immutable visit files are not.
    (directory/'progress.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    if finished:
        result = dict(summary=summary, top_rows=winners(completed), records=sorted(completed, key=lambda r:r['row_index']))
        target = directory/'refined.json'
        if not target.exists():
            with target.open('x') as stream:
                json.dump(result, stream, allow_nan=False)
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
