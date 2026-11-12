"""Census or explicitly reuse native inclusion controls in a diagnostic replay."""

import argparse
import hashlib
import inspect
import json
import os
import pickle
import time
import types
from copy import deepcopy
from pathlib import Path

from census_algo07v5_initial_controls import differences, fingerprint
from evaluate_algo07 import source_binding
from probe_algo07v5_annotation_rounds import cpu, load_context, request_inputs

from leo.analysis.localization_v3 import inclusion_controls, recovery_controller
from leo.analysis.localization_v3.scan import ScanLikelihood
from leo.analysis.localization_v4.backend import ProcessBound, read_manifest, validate_manifest
from leo.application.localization_v3_engine import _json_value
from leo.contracts.digests import canonical_digest
from leo.operations.localization_v3_job import stage_deadline
from leo.operations.localization_v3_parallel import (
    map_annotation_training,
    map_grid_batches,
    map_initial_arms,
    map_predictive_folds,
)


def prospective_key(kind, context, inventory, count, option, backend, binding):
    """Retain geometry and all mutable scientific state; bind the known backend."""
    scan = context['scan']
    if (context.get('numerical_policy') is not None or 'problem_factory' in context
            or type(scan) is not ScanLikelihood or (kind == 'fit_shared' and option)
            or getattr(scan, 'bound', None) is not backend
            or any(callable(value) for name, value in vars(scan).items() if name != 'bound')):
        return None
    if canonical_digest(backend.manifest) != binding:
        raise ValueError('Known numerical backend binding changed')
    state = dict(vars(scan))
    if not 0 < count <= len(state['tracks']):
        return None
    state['bound'] = dict(manifest_sha256=binding)
    for name in ('tracks', 'white', 'rx_basis'):
        state[name] = state[name][:count]
    if any(entry['track_index'] >= count for entry in context['entries']):
        return None
    value = dict(kind=kind, option=option, count=count, scan=state,
                 context={name: context[name] for name in
                          ('node', 'keep', 'powers', 'means', 'model', 'entries')},
                 policy=inventory['policy'])
    try:
        raw = json.dumps(inclusion_controls._fingerprint(value), sort_keys=True).encode()
    except TypeError:
        return None
    return hashlib.sha256(raw).hexdigest()


class ControlCensus:
    """Default to independent computations; diagnostic reuse returns isolated copies."""

    def __init__(self, backend, reuse=False):
        if type(reuse) is not bool:
            raise ValueError('Explicit boolean reuse selection required')
        self.reuse = reuse
        self.backend, self.binding = backend, canonical_digest(backend.manifest)
        self.original = inclusion_controls.InclusionControlCache()
        self.values, self.rows = {}, []

    def context(self, context, kind, option):
        return self.original.context(context, kind, option)

    def pair(self, compute, control, kind, context, inventory, count, option):
        if not control:
            return compute()
        if inclusion_controls.control_key(kind, context, inventory, count, option) is not None:
            raise ValueError('Current native cache bypass no longer holds; review census')
        began = time.perf_counter()
        key = prospective_key(kind, context, inventory, count, option, self.backend, self.binding)
        key_seconds = time.perf_counter() - began
        duplicate = key is not None and key in self.values
        reused = self.reuse and duplicate
        began, used = time.perf_counter(), cpu()
        value = deepcopy(self.values[key]) if reused else compute()
        seconds, cpu_seconds = time.perf_counter() - began, sum(cpu()) - sum(used)
        actual = fingerprint(value)
        if duplicate and actual != fingerprint(self.values[key]):
            raise ValueError('Equal prospective keys produced different complete control pairs')
        if key is not None and not duplicate:
            self.values[key] = deepcopy(value)
        self.rows.append(dict(kind=kind, option=option, key=key, key_seconds=key_seconds,
                              duplicate=duplicate, reused=reused, seconds=seconds,
                              cpu_seconds=cpu_seconds, complete_pair_sha256=actual))
        return value

    def summary(self):
        return dict(controls=len(self.rows), keyable=sum(r['key'] is not None for r in self.rows),
                    distinct_keys=len(self.values),
                    duplicates=sum(r['duplicate'] for r in self.rows),
                    duplicate_compute_seconds=sum(r['seconds'] for r in self.rows
                                                  if r['duplicate'] and not r['reused']),
                    duplicate_compute_cpu_seconds=sum(r['cpu_seconds'] for r in self.rows
                                                      if r['duplicate'] and not r['reused']),
                    reused_controls=sum(r['reused'] for r in self.rows),
                    independent_duplicate_comparisons=sum(r['duplicate'] and not r['reused']
                                                          for r in self.rows),
                    cached_copy_seconds=sum(r['seconds'] for r in self.rows if r['reused']),
                    key_seconds=sum(r['key_seconds'] for r in self.rows), cache_reuse=self.reuse,
                    geometry_fingerprinted=True,
                    savings_qualification=('diagnostic replay only; no worker speedup claim'
                                           if self.reuse else 'potential duplicate compute cost'))


def controller(census):
    original = recovery_controller.recover_tracks
    namespace = dict(original.__globals__, InclusionControlCache=lambda: census)
    if {key for key in namespace if namespace[key] is not original.__globals__[key]} != {
        'InclusionControlCache'
    }:
        raise ValueError('Only the explicit cache factory may change')
    operation = types.FunctionType(original.__code__, namespace, original.__name__,
                                   original.__defaults__, original.__closure__)
    operation.__kwdefaults__ = original.__kwdefaults__
    return operation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--native-manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, choices=range(1, 301), default=180)
    parser.add_argument('--reuse', action='store_true',
                        help='Reuse matching controls in this probe')
    parser.add_argument('--runtime', action='store_true',
                        help='Use the registered v5 cache factory through its real port')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.is_relative_to('/mnt/qnap01') or output.exists():
        parser.error('Fresh local output required')
    if args.runtime and not args.reuse:
        parser.error('Runtime factory requires explicit --reuse')
    request, job, store = request_inputs(args.request)
    manifest = validate_manifest(read_manifest(args.native_manifest))
    if request.get('backend_manifest') != manifest:
        parser.error('Native request must bind the same manifest')
    source_root = Path(__file__).resolve().parents[1] / 'src'
    modules = source_binding(source_root)
    paths = [args.request, args.native_manifest, Path(__file__),
             Path(__file__).with_name('probe_algo07v5_annotation_rounds.py'),
             Path(__file__).with_name('census_algo07v5_initial_controls.py'),
             Path(__file__).with_name('evaluate_algo07.py')]
    bindings = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in paths}
    plan = dict(status='plan', request_sha256=canonical_digest(request),
                manifest_sha256=canonical_digest(manifest), modules=modules, bindings=bindings,
                timeout_s=args.timeout, cache_reuse=args.reuse, runtime_factory=args.runtime,
                geometry_fingerprinted=True,
                GPS_used=False, whole_worker_speedup=None,
                scope='complete predictive recovery with diagnostic inclusion controls')
    output.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2, default=_json_value) + '\n')

    save('plan.json', plan)
    save('controller-source.json',
         dict(source=inspect.getsource(recovery_controller.recover_tracks)))
    if not args.run:
        print(json.dumps(dict(status='plan', output=str(output), archive_loaded=False)))
        return 0
    began = time.perf_counter()
    try:
        if len(os.sched_getaffinity(0)) != 3 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
            raise ValueError('Pin exactly three CPUs and one BLAS thread')
        stages, selections = [], []
        with stage_deadline(args.timeout):
            backend = ProcessBound(manifest, output / 'native-receipts')
            context, evidence, scientific = load_context(request, job, store, backend)
            census = ControlCensus(backend, reuse=args.reuse)
            control_factory = None
            if args.runtime:
                from leo.contracts.localization_v5 import inclusion_control_policy
                from leo.operations.localization_v5_controls import ControlCacheFactory

                control_factory = ControlCacheFactory(backend, inclusion_control_policy())
                operation = recovery_controller.recover_tracks
            else:
                operation = controller(census)

            def stage(name, operation):
                start, used = time.perf_counter(), cpu()
                value = operation()
                stages.append(dict(name=name, seconds=time.perf_counter() - start,
                                   cpu_seconds=sum(cpu()) - sum(used)))
                return True, value

            options = {}
            if control_factory is not None:
                options['inclusion_control_factory'] = control_factory
            policy = request.get('annotation_training_policy')
            if policy:
                from leo.analysis.localization_v5 import annotation_fallback, annotation_training
                fits = {fit.policy['id']: fit for fit in (annotation_training.fit,
                                                         annotation_fallback.fit)}
                fit = fits[policy['id']]
                if fit.policy != policy:
                    raise ValueError('Runtime training policy differs from the saved request')
                options['annotation_training_fit'] = fit
            start, used = time.perf_counter(), cpu()
            result = operation(
                context, evidence, run_stage=stage, discovery_allowed=lambda: True,
                on_selection=selections.append, map_annotation_folds=map_predictive_folds,
                map_annotation_training=map_annotation_training,
                map_inclusion_arms=map_initial_arms,
                map_joint_batches=map_grid_batches, map_joint_arms=map_initial_arms, **options)
            seconds, cpu_seconds = time.perf_counter() - start, sum(cpu()) - sum(used)
        raw = pickle.dumps(result, protocol=5)
        (output / 'recovery.pickle').write_bytes(raw)
        save('controls.json', census.rows)
        save('stages.json', stages)
        saved = store(job['output_root']).load(job['identity']['run_id'])
        issues = differences(saved['evidence']['audit']['predictive_recovery'], result)
        save('differences.json', issues)
        if issues:
            raise ValueError('Observed complete recovery differs from the saved native audit')
        if (source_binding(source_root) != modules or any(
                hashlib.sha256(Path(path).read_bytes()).hexdigest() != value
                for path, value in bindings.items())):
            raise ValueError('Bound source/input changed during census')
        validate_manifest(manifest)
        work = control_factory.provenance() if control_factory is not None else None
        summary = (dict(work['counts'], cache_reuse=True) if work is not None else census.summary())
        row = dict(plan, status='complete', scientific=scientific, seconds=seconds,
                   cpu_seconds=cpu_seconds, saved_audit_exact=True,
                   recovery_sha256=fingerprint(result),
                   pickle_sha256=hashlib.sha256(raw).hexdigest(), summary=summary,
                   **({'inclusion_control_work': work} if work is not None else {}),
                   native_activation=backend.provenance())
        save('result.json', row)
    except BaseException as exc:
        save('failure.json', dict(status='failed', error=type(exc).__name__, message=str(exc),
                                 seconds=time.perf_counter() - began))
        raise
    print(json.dumps(dict(status='complete', output=str(output), seconds=seconds,
                          cpu_seconds=cpu_seconds, summary=row['summary'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
