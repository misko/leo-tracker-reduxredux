"""Compare complete recovery from one freshly computed native prefix.

External diagnostic only. Fork each trial from the unchanged parent checkpoint;
do not reconstruct it from published results or serialize live solver closures.
The archived queue candidate is loaded in a private module namespace. Scientific
budgets and the current runtime implementation are never edited.
"""

import argparse
import hashlib
import json
import os
import resource
import time
from pathlib import Path
from unittest.mock import patch

from check_algo07v3_scan_likelihood import fingerprint
from profile_algo07v3_training_queue import cpu, measured_mapper

from leo.analysis.localization_v3 import predictive_annotation, recovery_controller
from leo.application import localization_v3 as policy
from leo.operations.localization_v3_job import execute, runtime_versions, validate_request
from leo.operations.localization_v3_parallel import (
    _ordered,
    map_annotation_training,
    map_initial_arms,
    map_predictive_folds,
)


class ProbeComplete(BaseException):
    """Stop the external native job before downstream fitting/publication."""


def signature(value):
    return hashlib.sha256(json.dumps(fingerprint(value), sort_keys=True).encode()).hexdigest()


def archived_candidate(root):
    bindings = json.loads((root / 'native-0/candidate-sources.json').read_bytes())
    modules = {}
    for name in ('predictive_annotation', 'recovery_controller', 'parallel'):
        relative = ('leo/operations/localization_v3_parallel.py' if name == 'parallel'
                    else f'leo/analysis/localization_v3/{name}.py')
        path = root / 'candidate-src' / relative
        source = path.read_bytes()
        if hashlib.sha256(source).hexdigest() != bindings[relative]:
            raise ValueError('Archived candidate source changed')
        scope = {'__name__': '_external_queue_' + name}
        if name == 'recovery_controller':
            annotation = modules['predictive_annotation']
            with patch.object(predictive_annotation, 'annotate', annotation['annotate']), \
                 patch.object(predictive_annotation, 'prepare_training_batch',
                              annotation['prepare_training_batch'], create=True):
                exec(compile(source, str(path), 'exec'), scope)
        else:
            exec(compile(source, str(path), 'exec'), scope)
        modules[name] = scope
    return modules['recovery_controller']['recover_tracks'], \
        modules['parallel']['map_all_target_training']


def recovery_trial(prepared, operation, global_mapper=None):
    """Run every original recovery stage; diagnostics cannot become rejection."""
    context, evidence = prepared['recovery_context'], prepared['inventory']
    if context.get('numerical_policy') is not None:
        raise ValueError('Stateful replay is outside this experiment')
    blocks, stages, values, selections = [], [], {}, []
    current = [None]

    def mapped(mapper, kind):
        def run(fn, items):
            before = len(blocks)
            output = measured_mapper(mapper, blocks, kind)(fn, items)
            for block in blocks[before:]:
                block['stage'] = current[0]
            return output
        return run

    def stage(name, fn):
        current[0] = name
        began, used = time.perf_counter(), cpu()
        value = fn()
        stages.append(dict(name=name, seconds=time.perf_counter() - began,
                           cpu_seconds=cpu() - used))
        values[name] = value
        return True, value

    before = signature((context['node'], context['keep'], evidence))
    began, used = time.perf_counter(), cpu()
    result = operation(
        context, evidence, run_stage=stage, discovery_allowed=lambda: True,
        on_selection=selections.append,
        map_annotation_training=mapped(map_annotation_training, 'training'),
        map_annotation_folds=mapped(map_predictive_folds, 'scoring'),
        map_inclusion_arms=mapped(map_initial_arms, 'inclusion'),
        **({'map_all_target_training': mapped(global_mapper, 'training')}
           if global_mapper else {}))
    elapsed, used = time.perf_counter() - began, cpu() - used
    if result.get('failure'):
        raise ValueError('Recovery failed: ' + result['failure'])
    if before != signature((context['node'], context['keep'], evidence)):
        raise ValueError('Frozen scientific inputs changed')
    # Full values are retained until the clock stops; hashing cannot change
    # inter-stage work or be silently swallowed as a scientific rejection.
    return dict(seconds=elapsed, cpu_seconds=used, blocks=blocks, stages=stages,
                result_signature=signature(result), selection_signature=signature(selections),
                stage_signatures={k: signature(v) for k, v in values.items()},
                input_signature=before, decision=result['decision'],
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def fork_trials(prepared, operations, sequence, on_result):
    rows, expected = [], None
    for index, side in enumerate(sequence):
        operation, mapper = operations[side]
        def run(_, operation=operation, mapper=mapper):
            return recovery_trial(prepared, operation, mapper)
        row = _ordered(run, [0], workers=1)[0]
        science = {k: row[k] for k in ('result_signature', 'selection_signature',
                                       'stage_signatures', 'input_signature')}
        if expected is None:
            expected = science
        row.update(index=index, side=side, exact=science == expected)
        on_result(row)
        rows.append(row)
        if not row['exact']:
            raise ValueError('Full recovery checkpoint changed')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--candidate-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reverse', action='store_true')
    args = parser.parse_args()
    if len(os.sched_getaffinity(0)) != 3 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        parser.error('Pin three CPUs and one BLAS thread')
    request = validate_request(json.loads(args.request.read_bytes()))
    if request['runtime'] != runtime_versions():
        raise ValueError('Frozen runtime differs')
    args.output.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), Path(__file__), args.request,
             Path('tools/check_algo07v3_scan_likelihood.py'),
             Path('tools/profile_algo07v3_training_queue.py'),
             *args.candidate_report.glob('candidate-src/**/*.py'),
             args.candidate_report / 'native-0/candidate-sources.json']
    bundle = Path(request['native_input']['path']).parent
    manifest = json.loads((bundle / 'input-bindings.json').read_bytes())
    paths += [bundle / 'input-bindings.json']
    for name, sha in manifest['files'].items():
        path = (bundle / name).resolve()
        if (not path.is_relative_to(bundle.resolve())
                or hashlib.sha256(path.read_bytes()).hexdigest() != sha):
            raise ValueError('Frozen native input changed')
        paths.append(path)
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    candidate, mapper = archived_candidate(args.candidate_report)
    sequence = ['candidate', 'baseline'] if args.reverse else ['baseline', 'candidate']
    plan = dict(bindings=bindings, sequence=sequence, cpus=sorted(os.sched_getaffinity(0)),
                blas_threads=1, policy=request['execution_policy'],
                native_prefix_recomputed=True, runtime_modified=False,
                production_modified=False, full_pipeline_speedup=None)
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')

    def save(row):
        (args.output / f"{row['index']}-{row['side']}.json").write_text(
            json.dumps(row, indent=2) + '\n')
        fields = ('side', 'seconds', 'cpu_seconds', 'exact')
        print(json.dumps({k: row[k] for k in fields}), flush=True)

    def intercepted(prepared, **kwargs):
        print('Native prefix ready; comparing forked recovery trials', flush=True)
        rows = fork_trials(prepared, {'baseline': (recovery_controller.recover_tracks, None),
                                     'candidate': (candidate, mapper)}, sequence, save)
        (args.output / 'result.json').write_text(json.dumps(dict(plan=plan, rows=rows), indent=2))
        raise ProbeComplete()

    native_request = dict(request, output_root=str(args.output.resolve() / 'unused-publication'),
                          evaluation_reference=None)
    with (args.output / 'prefix.jsonl').open('x') as log:
        def emit(row):
            log.write(json.dumps(row) + '\n')
            log.flush()
            print(json.dumps(row), flush=True)
        with patch.object(policy, 'recover_predictive_checkpoint', intercepted):
            try:
                execute(native_request, emit=emit)
            except ProbeComplete:
                pass
            else:
                raise ValueError('Native prefix interception did not run')
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha for p, sha in bindings.items()):
        raise ValueError('Bound input/source changed during comparison')
    # Read prior science only after every fresh inference has finished.
    from leo.storage.localization_v3 import LocalizationV3Store
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    reference = signature(saved['evidence']['audit']['predictive_recovery'])
    rows = json.loads((args.output / 'result.json').read_bytes())['rows']
    if any(r['result_signature'] != reference for r in rows):
        raise ValueError('Native recovery differs from the qualified full-scan audit')
    (args.output / 'verified.json').write_text(json.dumps(dict(
        bindings_unchanged=True, saved_native_audit_exact=True,
        scientific_receipt=saved['sha256'], reference_signature=reference)))


if __name__ == '__main__':
    main()
