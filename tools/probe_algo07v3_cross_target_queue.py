"""External all-target training queue; validation-all-work only, no runtime edits.

Capture each unchanged annotate call at its training port, queue all independent
fold/arm jobs on the existing three-worker adapter, then replay each annotation
in original order with its own training recipes. No training problem is reused.
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_annotation_arms import load_context
from profile_algo07v3_training_queue import cpu, measured_mapper

from leo.analysis.localization_v3.predictive_annotation import annotate
from leo.operations.localization_v3_job import runtime_versions, source_bindings
from leo.operations.localization_v3_parallel import (
    map_annotation_training,
    map_initial_branches,
    map_predictive_folds,
)
from leo.storage.localization_v3 import LocalizationV3Store


class TrainingPlan(Exception):
    def __init__(self, operation, tasks):
        self.operation, self.tasks = operation, tuple(tasks)


def capture(operation, tasks):
    raise TrainingPlan(operation, tasks)


def replay(plan, records):
    if len(plan.tasks) != len(records):
        raise ValueError('Incomplete training recipes')

    def mapped(operation, tasks):
        if tuple(tasks) != plan.tasks:
            raise ValueError('Annotation training schedule changed')
        return records
    return mapped


def run_annotations(context, evidence, *, combined, blocks,
                    annotate_fn=annotate, training_mapper=map_annotation_training,
                    global_mapper=map_initial_branches, fold_mapper=map_predictive_folds):
    if context.get('numerical_policy') is not None:
        raise ValueError('Stateful numerical replay is outside this experiment')
    inventory = dict(evidence['inventory'], publication_support=evidence['publication_support'])
    targets = evidence['selected_targets']
    plans, completed = {}, {}

    def one(index, mapper):
        target = targets[index]
        return annotate_fn(context, inventory, target['track_id'],
                           inactive_fragment=target['inactive_fragment'],
                           map_training=mapper,
                           map_folds=measured_mapper(fold_mapper, blocks, f'scoring-{index}'))

    if combined:
        for index in range(len(targets)):
            try:
                completed[index] = one(index, capture)
            except TrainingPlan as plan:
                plans[index] = plan
        # Global labels describe contiguous independent calibration pairs. The
        # existing adapter validates and caps execution at three processes.
        entries = [(index, task) for index, plan in plans.items() for task in plan.tasks]
        tasks = [(k // 2, task[1]) for k, (_, task) in enumerate(entries)]

        def train(task):
            k = 2 * task[0] + int(task[1] == 'fitted_c')
            index, original = entries[k]
            return plans[index].operation(original)

        records = measured_mapper(global_mapper, blocks, 'training')(train, tasks) if tasks else []
        offset = 0
        for index, plan in plans.items():
            count = len(plan.tasks)
            completed[index] = one(index, replay(plan, records[offset:offset + count]))
            offset += count
        blocks.append(dict(kind='global_task_labels', entries=entries))
    else:
        for index in range(len(targets)):
            before = len(blocks)
            completed[index] = one(index, measured_mapper(training_mapper, blocks, 'training'))
            for block in blocks[before:]:
                block['target'] = index
    return [completed[index] for index in range(len(targets))]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--reverse', action='store_true')
    args = p.parse_args()
    if len(os.sched_getaffinity(0)) != 3 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        p.error('Pin three CPUs and one BLAS thread')
    request = json.loads(args.request.read_bytes())
    if (request['runtime'] != runtime_versions()
            or request['execution_policy'] != 'validation-all-work'):
        raise ValueError('Match the frozen runtime and validation-all-work policy')
    args.output.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__)]
    paths.extend(Path('tools') / n for n in (
        'probe_algo07v3_annotation_arms.py', 'check_algo07v3_scan_likelihood.py',
        'profile_algo07v3_training_queue.py'))
    bindings = {str(q.resolve()): hashlib.sha256(q.read_bytes()).hexdigest() for q in paths}
    bindings.update({r['path']: r['sha256'] for r in source_bindings().values()})
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    attempts = saved['evidence']['audit']['predictive_recovery']['attempts']
    votes = [fingerprint(a['annotation']) for a in attempts]
    del saved
    plan = dict(bindings=bindings, policy=request['execution_policy'],
                affinity=sorted(os.sched_getaffinity(0)), blas_threads=1,
                maximum_workers=3, expected_saved_votes=votes, reverse=args.reverse)
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    expected, rows = None, []
    for side in (('candidate', 'baseline') if args.reverse else ('baseline', 'candidate')):
        context, evidence, receipt = load_context(request)
        before = fingerprint((context['node'], context['keep'], evidence))
        blocks = []
        began, used = time.perf_counter(), cpu()
        values = run_annotations(context, evidence, combined=side == 'candidate', blocks=blocks)
        elapsed, used = time.perf_counter() - began, cpu() - used
        actual = fingerprint(values)
        if expected is None:
            expected = actual
        vote_exact = [fingerprint(v['result']['annotation']) for v in values] == votes
        unchanged = before == fingerprint((context['node'], context['keep'], evidence))
        row = dict(side=side, seconds=elapsed, cpu_seconds=used, blocks=blocks,
                   exact=actual == expected, saved_votes_exact=vote_exact,
                   signature=actual, scientific_receipt=receipt,
                   unchanged_inputs=unchanged)
        rows.append(row)
        (args.output / f'{side}.json').write_text(json.dumps(row, indent=2) + '\n')
        print(json.dumps({k: row[k] for k in ('side', 'seconds', 'cpu_seconds', 'exact',
                                            'saved_votes_exact', 'unchanged_inputs')}), flush=True)
        if not row['exact'] or not vote_exact or not row['unchanged_inputs']:
            raise ValueError('Complete annotation or frozen vote changed')
    if not all(hashlib.sha256(Path(q).read_bytes()).hexdigest() == sha
               for q, sha in bindings.items()):
        raise ValueError('Bound sources changed during experiment')
    (args.output / 'result.json').write_text(json.dumps(dict(
        plan=plan, rows=rows, exact=True, runtime_modified=False,
        production_modified=False, full_pipeline_speedup=None), indent=2) + '\n')


if __name__ == '__main__':
    main()
