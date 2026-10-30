"""Broaden supported predictive identities without changing their observations or splits."""
import argparse
import csv
import hashlib
import math
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from debug_fast_graph_unassociated import read, write
from run_supported_graph_inclusions import completed_rows, supported_jobs
from stress_joint_attachment import supervise


def qualified_ids(rows):
    """Use recorded RF qualification only, including position regressions."""
    return {r['track_id'] for r in rows if r['qualified'] == 'True' and r['final_variant'] == 'True'}


def matched_expansion(original, expanded):
    if original['track_id'] != expanded['track_id']:
        raise ValueError('different target')
    old = {f['seed']: f for f in original['folds']}
    new = {f['seed']: f for f in expanded['folds']}
    if set(old) != set(new) or len(old) != len(original['folds']) or len(new) != len(expanded['folds']):
        raise ValueError('different folds')
    counts = []
    for seed, before in old.items():
        after = new[seed]
        if before['split'] != after['split']:
            raise ValueError('different physical split')
        proposals = {p['norad']: p for p in after['proposals']}
        for p in before['proposals']:
            if p['norad'] not in proposals:
                raise ValueError('original competitor missing')
            q = proposals[p['norad']]
            if p['alias'] != q['alias'] or set(p['arms']) != set(q['arms']):
                raise ValueError('different alias or c arms')
            for arm, value in p['arms'].items():
                for key in ('negative_twice_log_density', 'rms_hz'):
                    x = value['scores']['conditional_target'][key]
                    y = q['arms'][arm]['scores']['conditional_target'][key]
                    if not math.isclose(x, y, rel_tol=1e-10, abs_tol=1e-7):
                        raise ValueError('original candidate score changed')
        counts.append(dict(seed=seed, original=len(before['proposals']), expanded=len(after['proposals'])))
    return counts


def run(args):
    rows, excluded, receipts = completed_rows(args.queue, args.attempts)
    reports = getattr(args, 'qualified_reports', None) or []
    if reports:
        ids = set().union(*(qualified_ids(list(csv.DictReader(p.open()))) for p in reports))
        if not ids <= {r['track_id'] for r in rows}:
            raise ValueError('qualified reports reference unavailable original annotations')
        rows = [r for r in rows if r['track_id'] in ids]
    if (excluded and not reports) or len(rows) > 32 or not 1 <= args.workers <= 8:
        raise ValueError('requires at most 32 complete selected cases and one to eight workers')
    results = {r['track_id']: read(args.queue / r['track_id'] / 'result.json') for r in rows}
    jobs = supported_jobs(rows, results, require_engine_member=False)
    if reports and len(jobs) != len(rows):
        raise ValueError('qualified report contains an unsupported original identity')
    args.output.mkdir(parents=True, exist_ok=False)
    sources = receipts + reports + [args.queue / j['track_id'] / name for j in jobs for name in ('result.json', 'protocol.json')]
    write(args.output / 'protocol.json', dict(jobs=jobs, source_root=str(args.queue),
        source_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        candidate_cap=12, selection=('all RF-qualified final trials in supplied reports, including position regressions' if reports else 'all supported identities in the specified completed batch')+'; no GPS selection',
        seconds_per_case=600, workers=args.workers, causal_only=True, production_changed=False))

    def work(job):
        tid = job['track_id']
        receipts = [read(args.queue / a / (tid + '-terminal.json')) for a in args.attempts
                    if (args.queue / a / (tid + '-terminal.json')).exists()]
        command = receipts[0]['command'].copy()
        command[0] = sys.executable
        command[command.index('--output') + 1] = str(args.output / tid)
        if '--candidates' in command:
            raise ValueError('original attempt already overrides candidate budget')
        command += ['--candidates', '12']
        result = dict(job=job, command=command,
            **supervise(command, args.output / (tid + '.log'), 600))
        if result['status'] == 'complete':
            result['matched_expansion'] = matched_expansion(results[tid], read(args.output / tid / 'result.json'))
        write(args.output / (tid + '-terminal.json'), result)
        print(job['label'], result['status'], flush=True)
        return result

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        execution = list(pool.map(work, jobs))
    write(args.output / 'execution.json', execution)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('queue', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--attempts', nargs='+', required=True)
    p.add_argument('--workers', type=int, default=8)
    p.add_argument('--qualified-reports', type=Path, nargs='+', help='Restrict to every RF-qualified final trial in these comparison CSVs')
    run(p.parse_args())
