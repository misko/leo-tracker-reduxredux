"""Measure actual predictive training/scoring intervals without changing task order."""

import argparse
import hashlib
import itertools
import json
import os
import resource
import time
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_annotation_arms import load_context

from leo.analysis.localization_v3.predictive_annotation import annotate
from leo.operations.localization_v3_job import runtime_versions
from leo.operations.localization_v3_parallel import map_annotation_training, map_predictive_folds
from leo.storage.localization_v3 import LocalizationV3Store


def cpu():
    return sum(r.ru_utime + r.ru_stime for r in (
        resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)))


def measured_mapper(mapper, rows, kind):
    def run(operation, items):
        items = tuple(items)

        def measured(item):
            began, used = time.perf_counter(), time.process_time()
            value = operation(item)
            row = dict(item=item, start=began, end=time.perf_counter(),
                       cpu_seconds=time.process_time() - used,
                       max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            if kind == 'training':
                row['training_points'] = int(value['keep'].sum())
                row['phase_changes'] = [r['phase_change_s'] for r in value['metadata']['history']]
            return value, row

        began, used = time.perf_counter(), cpu()
        results = list(mapper(measured, items))
        rows.append(dict(kind=kind, start=began, end=time.perf_counter(),
                         cpu_seconds=cpu() - used, tasks=[r[1] for r in results]))
        return [r[0] for r in results]
    return run


def schedule_bounds(durations, workers=3):
    """An optimistic post-hoc scheduling bound, never an inference policy."""
    if not durations or len(durations) > 6 or any(t < 0 for t in durations):
        raise ValueError('One to six finite nonnegative task durations required')
    if workers != 3 or any(not float('-inf') < t < float('inf') for t in durations):
        raise ValueError('Three workers and finite durations required')

    def makespan(order):
        slots = [0.] * workers
        for index in order:
            slot = min(range(workers), key=slots.__getitem__)
            slots[slot] += durations[index]
        return max(slots)

    orders = list(itertools.permutations(range(len(durations))))
    best = min(orders, key=makespan)
    return dict(fifo_seconds=makespan(range(len(durations))),
                optimistic_best_seconds=makespan(best), optimistic_best_order=best,
                lower_bound_seconds=max(max(durations), sum(durations) / workers),
                prescient=True, measured_speedup=None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target', type=int, default=1)
    args = parser.parse_args()
    if len(os.sched_getaffinity(0)) != 3 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        parser.error('Pin three CPUs and one BLAS thread')
    args.output.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), Path(__file__), args.request,
             Path('tools/check_algo07v3_scan_likelihood.py'),
             Path('tools/probe_algo07v3_annotation_arms.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(args.request.read_bytes())
    assert request['runtime'] == runtime_versions()
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    expected_vote = fingerprint(saved['evidence']['audit']['predictive_recovery']['attempts'][
        args.target]['annotation'])
    receipt = saved['sha256']
    del saved
    plan = dict(bindings=bindings, target=args.target, scientific_receipt=receipt,
                cpus=sorted(os.sched_getaffinity(0)), blas_threads=1, max_workers=3,
                expected_saved_vote=expected_vote, runtime_modified=False,
                sequence=['unobserved', 'observed'], profiling_not_speed_comparison=True)
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    trials, expected = [], None
    for side in ('unobserved', 'observed'):
        d, inv, _ = load_context(request)
        target = inv['selected_targets'][args.target]
        inventory = dict(inv['inventory'], publication_support=inv['publication_support'])
        before = fingerprint((d['node'], d['keep'], inv))
        blocks = []
        training_mapper, fold_mapper = map_annotation_training, map_predictive_folds
        if side == 'observed':
            training_mapper = measured_mapper(training_mapper, blocks, 'training')
            fold_mapper = measured_mapper(fold_mapper, blocks, 'scoring')
        began, used = time.perf_counter(), cpu()
        value = annotate(d, inventory, target['track_id'],
                         inactive_fragment=target['inactive_fragment'],
                         map_training=training_mapper, map_folds=fold_mapper)
        elapsed, used = time.perf_counter() - began, cpu() - used
        actual = fingerprint(value)
        if expected is None:
            expected = actual
        exact = actual == expected
        for block in blocks:
            durations = [r['end'] - r['start'] for r in block['tasks']]
            seconds = block['end'] - block['start']
            block['seconds'] = seconds
            block['occupied_task_seconds'] = sum(durations)
            block['three_slot_occupancy'] = sum(durations) / (3 * seconds)
            block['three_slot_idle_seconds'] = 3 * seconds - sum(durations)
            if durations:
                block['posthoc_bounds'] = schedule_bounds(durations)
        trial = dict(side=side, seconds=elapsed, cpu_seconds=used, blocks=blocks,
                     exact=exact, actual=actual,
                     saved_vote_exact=fingerprint(value['result']['annotation']) == expected_vote)
        trials.append(trial)
        (args.output / f'{side}.json').write_text(json.dumps(trial, indent=2) + '\n')
        assert exact and trial['saved_vote_exact']
        assert before == fingerprint((d['node'], d['keep'], inv))
        print(json.dumps({k: v for k, v in trial.items() if k != 'actual'}), flush=True)
    result = dict(plan=plan, trials=trials, runtime_modified=False,
                  full_pipeline_speedup=None, production_modified=False)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    print(json.dumps(dict(exact=True, trials=len(trials), output=str(args.output))), flush=True)


if __name__ == '__main__':
    main()
