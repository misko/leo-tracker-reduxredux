"""Four predeclared fixed-bank initialization fits; research orchestration only."""
# ruff: noqa: E402
from __future__ import annotations

import hashlib
import json
import sys
import time
import traceback
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPORTS / '2026_10_17_dsx01_iteration7/cold_saved_s01'))
sys.path.insert(0, str(REPORTS / '2026_10_17_dsx01_iteration5/joint_band_contrast'))
sys.path.insert(0, str(REPORTS / '2026_10_16_dsx01_models'))

from common import endpoint_status, refit
from contexts import load_contexts
from leo.analysis.hard60_bounded_fit import _Problem
from leo.application.shared_fast_position import plain
from model import free_context
from transport import seed_from_context

DONORS = ('original', 'saved_space_track')
ARMS = ('fitted-c', 'zero-c')


def digest(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(plain(value), stream, indent=2, allow_nan=False)
        stream.write('\n')


def freeze():
    saved = Path('/tmp/three-track-investigation/space-track-pipeline-rerun/output/terminal.json')
    document = json.loads(saved.read_text())
    paths = {Path(__file__), HERE/'transport.py', HERE/'test_transport.py',
             HERE/'PROTOCOL.md', saved,
             REPORTS/'2026_10_17_dsx01_iteration7/cold_saved_s01/contexts.py',
             REPORTS/'2026_10_16_dsx01_models/common.py',
             REPORTS/'2026_10_17_dsx01_iteration5/joint_band_contrast/model.py',
             REPORTS/'2026_10_16_dsx01_fast_association_losses/sources.json',
             REPORTS/'2026_10_16_dsx01_fast_association_losses/context-observations.jsonl'}
    paths.update(Path(binding['path']) for binding in document['stage_receipts'])
    paths.update(Path(module.__file__) for name, module in tuple(sys.modules.items())
                 if name.startswith('leo.') and getattr(module, '__file__', None)
                 and str(module.__file__).endswith('.py'))
    bindings = {str(path): digest(path) for path in sorted(paths)}
    save(HERE/'source_freeze.json', dict(files=bindings, donors=DONORS, arms=ARMS,
        outcomes=4, maximum_evaluations=1000, maximum_seconds=120,
        domain='Same broad regional prior; no extra donor-specific25km disk',
        source_selection='Two saved complete S01 providers; no window or location selection'))
    return bindings


def validate_seed(ctx, vector, nuisance, *, fixed_c):
    problem = _Problem(ctx.model, vector, rf_arm='zero-c' if fixed_c else 'fitted-c')
    if not problem.feasible(vector):
        raise ValueError('Infeasible transported physical state')
    limits = np.r_[np.full(ctx.model.clock_count, 2000.), ctx.model.group_limits]
    if nuisance.shape != limits.shape or np.any(abs(nuisance) > limits + 1e-7):
        raise ValueError('Infeasible transported nuisance state')
    if fixed_c and vector[6] != 0:
        raise ValueError('Nonzero c in constrained arm')
    canonicalization = float(np.max(abs(problem.start - vector)))
    if canonicalization > 2e-9:
        raise ValueError('Transport would require optimizer clipping or timing rescaling')
    return canonicalization


def qualify(contexts):
    target = free_context(contexts['saved_space_track'])
    native = contexts['saved_space_track']
    old = native.model.evaluate_joint(native.vector, native.nuisance)
    new = target.model.evaluate_joint(native.vector, target.nuisance)
    for a, b in ((old[0], new[0]), (old[1], new[1]),
                 (old[2], new[2][:len(old[2])]),
                 (old[3].responsibilities, new[3].responsibilities), (old[3].nll, new[3].nll)):
        np.testing.assert_allclose(a, b, rtol=0, atol=1e-8)
    seeds, rows = {}, []
    calls = 2
    for donor in DONORS:
        for arm in ARMS:
            source = contexts[donor]
            vector, nuisance, receipt = seed_from_context(source, source.vector, source.nuisance,
                                                         target, arm=arm)
            ctx = replace(target, vector=vector, nuisance=nuisance, fixed_c=arm == 'zero-c')
            canonicalization = validate_seed(ctx, vector, nuisance, fixed_c=ctx.fixed_c)
            ev = ctx.model.evaluate_joint(vector, nuisance)
            calls += 1
            derivative = []
            for j in range(ctx.model.band_count):
                at = ctx.model.original_nuisance_count + j
                plus, minus = nuisance.copy(), nuisance.copy()
                plus[at] += .01
                minus[at] -= .01
                fd = (ctx.model.evaluate_joint(vector, plus)[0]
                      - ctx.model.evaluate_joint(vector, minus)[0]) / .02
                calls += 2
                np.testing.assert_allclose(fd, ev[2][at], atol=2e-6, rtol=2e-5)
                derivative.append(dict(index=at, finite_difference=float(fd),
                                       analytic=float(ev[2][at])))
            rows.append(dict(donor=donor, arm=arm, transport=receipt,
                vector=vector, nuisance=nuisance,
                seed_objective=float(ev[0]), seed_nll=float(ev[3].nll),
                band_derivatives=derivative, feasible=True,
                existing_solver_boundary_interiorization_maximum=canonicalization))
            seeds[donor, arm] = ctx
    save(HERE/'qualification.json', dict(passed=True, calls=calls, rows=rows,
        native_nesting=True, reference_reads=False, observations=4797,
        candidate_numbers=target.bank.numbers,
        neutral_q=target.model.score.detection_budget / len(target.bank.numbers)))
    return seeds


def main():
    begun = time.monotonic()
    bindings = freeze()
    contexts = load_contexts(maximum_seconds=110.)
    preparation_s = time.monotonic() - begun
    seeds = qualify(contexts)
    # Bind late-loaded public dependencies before the first optimization call.
    dependencies = {str(Path(module.__file__)): digest(module.__file__)
                    for name, module in tuple(sys.modules.items())
                    if name.startswith('leo.') and getattr(module, '__file__', None)
                    and str(module.__file__).endswith('.py')}
    save(HERE/'qualified_freeze.json', dict(source_freeze_sha256=digest(HERE/'source_freeze.json'),
        qualification_sha256=digest(HERE/'qualification.json'), files=dependencies,
        preparation_seconds=preparation_s, preparation_public_endpoint_replay_calls=2,
        fitting_not_started=True))
    for path, sha in {**bindings, **dependencies}.items():
        if digest(path) != sha:
            raise ValueError('Frozen source changed: ' + path)
    fits = []
    for donor in DONORS:
        for arm in ARMS:
            ctx = seeds[donor, arm]
            result = refit(ctx, ctx.vector, ctx.nuisance, max_evaluations=1000,
                           max_seconds=120., fixed_c=ctx.fixed_c)
            audit = endpoint_status(ctx, result['vector'], result['nuisance'])
            row = dict(donor=donor, arm=arm, result=result, independent_audit=audit,
                       original_seed=dict(vector=ctx.vector, nuisance=ctx.nuisance),
                       reference_reads=False)
            path = HERE/f'fit_{donor}_{arm}.json'
            save(path, row)
            fits.append(dict(path=str(path), sha256=digest(path), donor=donor, arm=arm,
                             strict=bool(audit['accepted'])))
            print(json.dumps(dict(donor=donor, arm=arm, strict=bool(audit['accepted']),
                evaluations=result['diagnostics']['evaluations'])), flush=True)
    save(HERE/'outcomes_seal.json', dict(outcomes=fits, all_four_sealed=True,
        source_freeze_sha256=digest(HERE/'source_freeze.json'),
        qualified_freeze_sha256=digest(HERE/'qualified_freeze.json'),
        elapsed_seconds=time.monotonic()-begun, observations=4797, candidate_count=59,
        reference_reads=False, evaluation_not_started=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        save(HERE/'failure.json', dict(type=type(error).__name__, message=str(error),
            traceback=traceback.format_exc(), no_automatic_retry=True))
        raise
