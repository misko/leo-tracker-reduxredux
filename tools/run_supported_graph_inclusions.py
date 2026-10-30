"""Bounded original-model inclusion trials for supported graph annotations."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import hashlib
import sys

from debug_fast_graph_unassociated import read, write
from leo.analysis.research.grouped_prediction import identity_consensus
from stress_joint_attachment import supervise


def supported_jobs(rows, results, *, require_engine_member=True):
    jobs = []
    seen = set()
    for row in rows:
        tid = row['track_id']
        if tid in seen:
            raise ValueError('repeated track in frozen attempts')
        seen.add(tid)
        result = results[tid]
        annotation = identity_consensus(result['folds'], score_name=result.get('identity_score_name', 'joint'))
        if (row['engine_member'] or not require_engine_member) and annotation['status'] == 'conditionally_supported_identity':
            jobs.append(dict(row, annotation=annotation))
    return jobs


def completed_rows(queue, attempts):
    completed=[];excluded=[];sources=[];seen=set()
    for attempt in attempts:
        for row in read(queue/attempt/'selected.json'):
            tid=row['track_id']
            if tid in seen:raise ValueError('repeated track in frozen attempts')
            seen.add(tid);path=queue/attempt/(tid+'-terminal.json')
            if not path.exists():raise ValueError('annotation attempt is not terminal')
            receipt=read(path);sources.append(path)
            if receipt['status']=='complete':completed.append(row)
            else:excluded.append(dict(track_id=tid,label=row['label'],execution=receipt['status'],reason=receipt.get('reason')))
    return completed,excluded,sources


def run(args):
    if not 1 <= args.workers <= 16:
        raise ValueError('worker bound is 1..16')
    rows,excluded,terminal_sources=completed_rows(args.queue,args.attempts)
    if len(rows)+len(excluded) > 32:
        raise ValueError('one bounded iteration contains at most 32 annotations')
    results = {r['track_id']: read(args.queue / r['track_id'] / 'result.json') for r in rows}
    jobs = supported_jobs(rows, results)
    args.output.mkdir(parents=True, exist_ok=False)
    sources = {str(args.queue / r['track_id'] / 'result.json'):
               hashlib.sha256((args.queue / r['track_id'] / 'result.json').read_bytes()).hexdigest() for r in rows}
    sources.update({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in terminal_sources})
    write(args.output / 'protocol.json', dict(jobs=jobs, annotation_sources=sources, attempts=args.attempts,
          incomplete_annotation_exclusions=excluded,
          queue=str(args.queue), workers=args.workers, seconds_per_case=600,
          selection='Every supported engine-member identity with a complete annotation; incomplete executions recorded separately',
          original_model_and_noise=True, GPS_used=False, future_TLE=False, matched_c_arms=True))

    def work(job):
        tid = job['track_id']
        command = [sys.executable, str(Path(__file__).with_name('include_curved_family_annotations.py')),
                   '--inventory', job['inventory'], '--validation', str(args.queue / tid),
                   '--output', str(args.output / tid)]
        result = dict(track_id=tid, label=job['label'], command=command,
                      **supervise(command, args.output / (tid + '.log'), 600))
        write(args.output / (tid + '-terminal.json'), result)
        return result

    print('supported graph inclusion jobs', len(jobs), flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(work, job) for job in jobs]):
            print(future.result(), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queue', type=Path, required=True)
    parser.add_argument('--attempts', nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=8)
    run(parser.parse_args())
