"""Bounded replay through the real annotation port and production training queue."""

import argparse
import hashlib
import json
import os
import pickle
import time
from pathlib import Path

import numpy as np
from census_algo07v5_initial_controls import fingerprint
from evaluate_algo07 import source_binding
from probe_algo07v5_annotation_rounds import (
    compare,
    cpu,
    load_context,
    metrics,
    read_reference,
    request_inputs,
)

from leo.analysis.localization_v3.predictive_annotation import annotate
from leo.analysis.localization_v4.backend import ProcessBound, read_manifest, validate_manifest
from leo.analysis.localization_v5.annotation_training import fit as annotation_fit
from leo.application.localization_v3_engine import _json_value
from leo.contracts.digests import canonical_digest
from leo.operations.localization_v3_job import stage_deadline
from leo.operations.localization_v3_parallel import map_annotation_training, map_predictive_folds


def work_counts(annotation):
    rounds, optimizer = [], []
    for fold in annotation['result']['folds']:
        proposals = fold['proposals']
        if not proposals:
            return dict(available=False, reason='A fold has no retained training metadata')
        for arm in ('c0', 'fitted_c'):
            history = proposals[0]['arms'][arm]['history']
            if any(fingerprint(p['arms'][arm]['history']) != fingerprint(history)
                   for p in proposals):
                raise ValueError('Proposals disagree on shared fold/arm training')
            rounds.append(len(history))
            optimizer.extend(row['optimizer'] for row in history if 'optimizer' in row)
    if optimizer and len(optimizer) != sum(rounds):
        raise ValueError('Incomplete per-round optimizer work metadata')
    return dict(available=True, training_calls=len(rounds), phase_rounds=rounds,
                completed_rounds=sum(rounds), recorded_optimizer_calls=len(optimizer),
                optimizer_work_available=bool(optimizer),
                residual_evaluations=(sum(r['evaluations'] for r in optimizer)
                                      if optimizer else None),
                reported_convergences=(sum(r['converged'] for r in optimizer)
                                       if optimizer else None),
                budget_exhaustions=(sum(r['budget_exhausted'] for r in optimizer)
                                    if optimizer else None),
                stationarity_satisfied=(sum(r.get('stationarity', {}).get('satisfied') is True
                                            for r in optimizer) if optimizer else None))


def scientific_gate(baseline, candidate):
    def proposals(value):
        return {(r['seed'], r['arm'], r['norad']): r['alias']
                for r in value['metrics']['proposals']}

    def votes(value):
        return [{k: row[k] for k in ('seed', 'arm', 'norad', 'runner_up', 'adequate')}
                for row in value['metrics']['consensus']['votes']]

    return dict(nominees=baseline['metrics']['nominees'] == candidate['metrics']['nominees'],
                proposal_aliases=proposals(baseline) == proposals(candidate),
                votes=votes(baseline) == votes(candidate),
                consensus=all(baseline['metrics']['consensus'][k]
                              == candidate['metrics']['consensus'][k]
                              for k in ('status', 'norad')))


def qualify_reference(receipt, plan):
    keys = ('request_sha256', 'target', 'manifest_sha256', 'modules', 'bindings')
    if (receipt['status'] != 'complete' or receipt['optimizer'] != 'gn'
            or any(receipt[k] != plan[k] for k in keys)):
        raise ValueError('Complete GN reference with the same source and inputs required')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--native-manifest', type=Path, required=True)
    parser.add_argument('--target', type=int, required=True)
    parser.add_argument('--optimizer', choices=('gn', 'lbfgsb'), default='gn')
    parser.add_argument('--execution', choices=('folds', 'queued'), default='queued')
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, choices=range(1, 121), default=120)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.is_relative_to('/mnt/qnap01') or output.exists() or args.target < 0:
        parser.error('Fresh local output and nonnegative target index required')
    if args.run and args.optimizer != 'gn' and args.reference is None:
        parser.error('Candidate requires a complete current-source GN reference')
    request, job, store = request_inputs(args.request)
    manifest = validate_manifest(read_manifest(args.native_manifest))
    if 'backend_manifest' in request and request['backend_manifest'] != manifest:
        parser.error('Manifest differs from the saved request')
    paths = [args.request, args.native_manifest, Path(__file__),
             Path(__file__).with_name('probe_algo07v5_annotation_rounds.py'),
             Path(__file__).with_name('census_algo07v5_initial_controls.py'),
             Path(__file__).with_name('evaluate_algo07.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    source_root = Path(__file__).resolve().parents[1] / 'src'
    modules = source_binding(source_root)
    plan = dict(status='plan', optimizer=args.optimizer, execution=args.execution,
                target=args.target, request_sha256=canonical_digest(request),
                manifest_sha256=canonical_digest(manifest), modules=modules, bindings=bindings,
                timeout_s=args.timeout, phase_rounds=5, position_steps=48, folds=3,
                candidates=12, GPS_used=False, accuracy_qualification=False,
                scope='complete annotation through runtime fit port', whole_worker_speedup=None)
    output.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2, default=_json_value) + '\n')

    save('plan.json', plan)
    if not args.run:
        print(json.dumps(dict(status='plan', output=str(output))))
        return 0
    began = time.perf_counter()
    try:
        if len(os.sched_getaffinity(0)) != 3 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
            raise ValueError('Pin three CPUs and one BLAS thread')
        reference = reference_receipt = None
        if args.reference:
            reference_receipt, reference = read_reference(args.reference.resolve())
            qualify_reference(reference_receipt, plan)
        with stage_deadline(args.timeout):
            backend = ProcessBound(manifest, output / 'native-receipts')
            context, evidence, scientific = load_context(request, job, store, backend)
            if reference_receipt is not None and reference_receipt['scientific'] != scientific:
                raise ValueError('Reference reconstructed a different scientific context')
            target = evidence['selected_targets'][args.target]
            inventory = dict(evidence['inventory'],
                             publication_support=evidence['publication_support'])
            options = {}
            if args.optimizer == 'lbfgsb':
                options['training_fit'] = annotation_fit
            fit_began, fit_cpu = time.perf_counter(), cpu()
            annotation = annotate(context, inventory, target['track_id'],
                inactive_fragment=target['inactive_fragment'], candidates=12, folds=3,
                phase_step=.1, shifted_origin=True, map_folds=map_predictive_folds,
                map_training=map_annotation_training if args.execution == 'queued' else None,
                **options)
            seconds, used = time.perf_counter() - fit_began, np.subtract(cpu(), fit_cpu).tolist()
        raw = pickle.dumps(annotation, protocol=5)
        (output / 'annotation.pickle').write_bytes(raw)
        row = dict(plan, status='complete', scientific=scientific, target_record=target,
                   annotation_seconds=seconds, annotation_cpu_seconds=used,
                   annotation_sha256=fingerprint(annotation),
                   pickle_sha256=hashlib.sha256(raw).hexdigest(), metrics=metrics(annotation),
                   work_counts=work_counts(annotation), native_activation=backend.provenance())
        if reference is not None:
            assessment = compare(reference, annotation)
            save('comparison.json', assessment)
            row.update(exact=assessment['exact'],
                       scientific_gate=scientific_gate(reference_receipt, row))
            if args.optimizer == 'gn' and not assessment['exact']:
                raise ValueError('Queued GN annotation differs from the ordinary fold path')
        if (source_binding(source_root) != modules or any(
                hashlib.sha256(Path(p).read_bytes()).hexdigest() != value
                for p, value in bindings.items())):
            raise ValueError('Bound source/input changed during experiment')
        save('result.json', row)
    except BaseException as exc:
        save('failure.json', dict(status='failed', error=type(exc).__name__, message=str(exc),
                                 seconds=time.perf_counter() - began))
        raise
    print(json.dumps(dict(status='complete', output=str(output), seconds=seconds,
                          cpu_seconds=sum(used), scientific_gate=row.get('scientific_gate'))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
