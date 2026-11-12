"""Replay a captured joint experiment, deferring factorized fits until needed."""

import argparse
import hashlib
import json
import os
import pickle
from pathlib import Path

from census_algo07v5_initial_controls import differences, fingerprint
from evaluate_algo07 import source_binding
from probe_algo07v5_annotation_rounds import load_context, request_inputs
from probe_algo07v5_joint_start import ARMS, CHECKOUT, elapsed, trial_summary

from leo.analysis.localization_v3.joint_fits import DeferredJointFits
from leo.analysis.localization_v3.joint_recovery import (
    audit_joint,
    fit_joint,
    joint_numerical_only,
)
from leo.analysis.localization_v4.backend import ProcessBound, read_manifest, validate_manifest
from leo.application.localization_v3_engine import _json_value
from leo.contracts.digests import canonical_digest
from leo.operations.localization_v3_job import stage_deadline
from leo.operations.localization_v3_parallel import map_grid_batches, map_initial_arms


def joint_passes(experiment):
    return all(experiment[m][a]['audit']['RF_qualified_arm']
               for m in ('control', 'joint') for a in ARMS)


def needs_factorized(experiment):
    """A passed joint or an irreparable partial audit makes retry irrelevant."""
    if any(m not in experiment or set(experiment[m]) != set(ARMS)
           for m in ('control', 'joint')):
        raise ValueError('Both complete control and joint arms required')
    if joint_passes(experiment):
        return False
    return all(
        not record['audit']['incumbent_owner_changes']
        and record['audit']['phase_check']['phase_change_s'] <= .01
        and all(v['all_pass'] for v in record['audit']['exact_incumbent_orbits'])
        and all(v for k, v in record['audit']['checks'].items()
                if k != 'incumbent_and_numerical')
        for method in ('control', 'joint')
        for record in experiment[method].values()
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--native-manifest', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, choices=range(1, 301), default=180)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    output, reference = args.output.resolve(), args.reference.resolve()
    if output.exists() or output.is_relative_to('/mnt/qnap01'):
        parser.error('Fresh local output required')
    request, job, store = request_inputs(args.request)
    manifest = validate_manifest(read_manifest(args.native_manifest))
    reference_plan = json.loads((reference / 'plan.json').read_bytes())
    reference_result = json.loads((reference / 'result.json').read_bytes())
    reference_scientific = json.loads((reference / 'scientific-binding.json').read_bytes())
    raw = (reference / 'captured.pickle').read_bytes()
    root = CHECKOUT / 'src'
    modules = source_binding(root)
    if (reference_result['status'] != 'complete'
            or not reference_result['complete_recovery_exact']
            or hashlib.sha256(raw).hexdigest() != reference_result['captured_sha256']
            or reference_plan['modules'] != modules
            or request.get('backend_manifest') != manifest
            or reference_plan['request_sha256'] != canonical_digest(request)
            or reference_plan['manifest_sha256'] != canonical_digest(manifest)):
        raise ValueError('A complete unchanged original recovery capture is required')
    bindings = dict(reference_plan['bindings'])
    bindings[str(Path(__file__).resolve())] = hashlib.sha256(
        Path(__file__).read_bytes()).hexdigest()

    def verify():
        if source_binding(root) != modules or any(
                hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha
                for p, sha in bindings.items()):
            raise ValueError('Measured runtime, tools or inputs changed')

    verify()
    output.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2, default=_json_value) + '\n')

    save('plan.json', dict(status='plan', modules=modules, bindings=bindings,
                          reference=str(reference), timeout_seconds=args.timeout,
                          GPS_used=False, optimizer_and_phase_budgets_unchanged=True,
                          scope='original joint experiment only; no complete-worker claim'))
    if not args.run:
        print(json.dumps(dict(status='plan', output=str(output), archive_loaded=False)))
        return 0
    if len(os.sched_getaffinity(0)) != 3 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        raise ValueError('Exactly three CPUs and single-thread BLAS required')
    captured = pickle.loads(raw)
    experiment, stages, issues = {}, [], []
    try:
        with stage_deadline(args.timeout):
            backend = ProcessBound(manifest, output / 'native-receipts')
            context, evidence, scientific = load_context(request, job, store, backend)
            if fingerprint(reference_scientific) != fingerprint(scientific):
                raise ValueError('Scientific reconstruction differs from the capture')
            inventory = dict(evidence['inventory'],
                             publication_support=evidence['publication_support'])
            for method in ('control', 'joint', 'factorized'):
                if method == 'factorized' and not needs_factorized(experiment):
                    break
                experiment[method] = {}
                fits = DeferredJointFits(context, captured['joint-probe'], method, 'lbfgsb',
                                         fit_joint, map_initial_arms)
                for arm in ARMS:
                    name = method + '-' + arm
                    trial, timing = elapsed(lambda arm=arm, fits=fits: fits.fit(arm))
                    stages.append(dict(name=name, **timing))
                    control = experiment['control'].get(arm, {}).get('audit')
                    audit, timing = elapsed(lambda trial=trial, control=control: audit_joint(
                        context, inventory, trial, control, map_batches=map_grid_batches))
                    stages.append(dict(name=name + '-audit', **timing))
                    experiment[method][arm] = dict(trial=trial, audit=audit)
                    issues.extend(differences(captured[name], trial, '$[' + repr(name) + ']'))
                    issues.extend(differences(captured[name + '-audit'], audit,
                                              '$[' + repr(name + '-audit') + ']'))
                    save('stages.json', stages)
            original = {m: {a: dict(trial=captured[m + '-' + a],
                                   audit=captured[m + '-' + a + '-audit']) for a in ARMS}
                        for m in ('control', 'factorized', 'joint')}
            passed, original_passed = joint_passes(experiment), joint_passes(original)
            retry = (not passed and 'factorized' in experiment
                     and joint_numerical_only(experiment))
            original_retry = not original_passed and joint_numerical_only(original)
            if (passed, bool(retry)) != (original_passed, bool(original_retry)):
                raise ValueError('Joint acceptance or numerical retry decision changed')
            save('differences.json', issues)
            if issues:
                raise ValueError('Remaining complete trials or audits are not bit exact')
            save('experiments.json', experiment)
            provenance = backend.provenance()
            keys = {k for r in provenance['receipts'] for k in r['counts']}
            native = {k: sum(r['counts'].get(k, 0) for r in provenance['receipts']) for k in keys}
            baseline_stages = json.loads((reference / 'stages.json').read_bytes())
            baseline_stages = [r for r in baseline_stages
                               if any(r['name'] == m + '-' + a + suffix
                                      for m in original for a in ARMS
                                      for suffix in ('', '-audit'))]
            summary = dict(status='complete', remaining_trials_and_audits_bitexact=True,
                           joint_passes=passed, numerical_retry_eligible=bool(retry),
                           factorized_computed='factorized' in experiment,
                           baseline={k: sum(r[k] for r in baseline_stages)
                                     for k in ('wall_seconds', 'cpu_seconds')},
                           candidate={k: sum(r[k] for r in stages)
                                      for k in ('wall_seconds', 'cpu_seconds')},
                           native_counts=native,
                           trials={m: {a: trial_summary(record['trial'], record['audit'])
                                       for a, record in rows.items()}
                                   for m, rows in experiment.items()},
                           whole_worker_speedup=None, GPS_used=False)
        verify()
        save('result.json', summary)
        print(json.dumps({k: v for k, v in summary.items() if k != 'trials'}), flush=True)
    except BaseException as error:
        save('stages.json', stages)
        save('differences.json', issues)
        save('result.json', dict(status='failed', error=type(error).__name__,
                                 message=str(error), whole_worker_speedup=None))
        raise
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
