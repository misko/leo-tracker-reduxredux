"""S01 nesting oracle and S03 matched conservative age-prior pilot."""

import argparse
import importlib
import importlib.util
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT/'reports/2026_10_16_dsx01_models'
PREVIOUS = ROOT/'reports/2026_10_16_dsx01_iteration2'
sys.path.insert(0, str(OLD))
common = importlib.import_module('common')


def load(name):
    spec = importlib.util.spec_from_file_location('age_pilot_'+name, HERE/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


age, profile_fit, calibration_port = load('model'), load('fit'), load('calibrate_v2')
digest = calibration_port.digest


class Counted:
    def __init__(self, model):
        self.model, self.calls = model, 0
    def __getattr__(self, name):
        return getattr(self.model, name)
    def evaluate_joint(self, *args):
        self.calls += 1
        return self.model.evaluate_joint(*args)
    def evaluate_details(self, *args):
        self.calls += 1
        return self.model.evaluate_details(*args)


def prepare(label):
    ctx = common.load_context(label)
    source = ctx.source
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    matching = [s for s in archive.list_snapshots()
        if s.digest == source['tle_sha256']
        and s.collected_utc_ns == source['tle_collected_utc_ns']]
    if len(matching) != 1 or matching[0].collected_utc_ns >= source['first_sample_estimate_utc_ns']:
        raise ValueError('unique original causal TLE authority required')
    snapshot = matching[0]
    catalogue = parse_element_sets(archive.read(snapshot))
    lookup = {int(n): i for i, n in enumerate(catalogue.satellite_numbers)}
    epochs = catalogue.element_epoch_utc_ns()
    selected_epochs = np.array([epochs[lookup[int(n)]] for n in ctx.bank.numbers], dtype=np.int64)
    ages = (source['first_sample_estimate_utc_ns']-selected_epochs)/86400e9
    calibration = json.loads((HERE/'calibration_v2.json').read_text())
    sigmas, statuses = age.widths(snapshot.provider, ages, calibration)
    parent_path = PREVIOUS/'results'/f'{label}-fitted-c-profile.json'
    parent = json.loads(parent_path.read_text())
    receipt = dict(provider=snapshot.provider, tle_digest=snapshot.digest,
        tle_collected_utc_ns=snapshot.collected_utc_ns,
        measurement_start_utc_ns=source['first_sample_estimate_utc_ns'],
        numbers=ctx.bank.numbers, element_epochs_utc_ns=selected_epochs,
        ages_days=ages, sigmas_s=sigmas, statuses=statuses,
        changed_widths=int(np.sum(sigmas != 2.)),
        parent_path=str(parent_path), parent_sha256=digest(parent_path),
        policy='>=100uniqueobjects/bin; MAD core clipped.5–2s; unsupportedbaseline2s',
        unsupported_fallback_may_be_nonmonotonic=True,
        uncertainty='conservative historical-consistency sensitivity, not physical Gaussian truth')
    return ctx, parent, sigmas, receipt


def freeze():
    paths = [HERE/f'{name}.py' for name in
             ('model', 'fit', 'run', 'test_model', 'test_fit', 'test_run')]
    paths += [HERE/'PRIOR_PROTOCOL.md', HERE/'calibration_v2.json', HERE/'calibrate_v2.py',
              age.PROFILE_SOURCE, OLD/'common.py']
    paths += [PREVIOUS/'results'/f'{label}-fitted-c-profile.json' for label in ('S01', 'S03')]
    authority = {str(p): digest(p) for p in paths}
    with (HERE/'pilot_plan.json').open('x') as stream:
        json.dump(dict(source_sha256=authority, labels=['S01', 'S03'],
            S01='exact model nesting only, zero fits; no unsupported HF extrapolation',
            S03='2priorfamilies x2RFarms x2methods =8 fits',
            maximum_objectives_per_fit=1000, maximum_seconds_per_fit=120,
            common_timing_sigma_s=3, floor_relative_sigma_s=.5, cap_relative_sigma_s=2,
            candidate_policy='same original fixed bank and calibration functions'),
            stream, indent=2)


def verify_authority():
    plan = json.loads((HERE/'pilot_plan.json').read_text())
    if any(digest(p) != sha for p, sha in plan['source_sha256'].items()):
        raise ValueError('frozen prior-pilot source authority changed')
    return plan


def qualify():
    from leo.analysis.hard60_bounded_fit import _Problem

    verify_authority()
    receipts = []
    for label in ('S01', 'S03'):
        ctx, parent, sigmas, metadata = prepare(label)
        v, n = np.array(parent['vector']), np.array(parent['nuisance'])
        scalar = age.RelativeTimingModel(ctx.model, 2.)
        target = age.RelativeTimingModel(ctx.model, sigmas)
        original = ctx.model.evaluate_joint(v, n)
        same = scalar.evaluate_joint(v, n)
        for a, b in zip(original[:3], same[:3], strict=True):
            np.testing.assert_array_equal(a, b)
        np.testing.assert_array_equal(original[3].responsibilities, same[3].responsibilities)
        changed = target.evaluate_joint(v, n)
        np.testing.assert_array_equal(original[3].responsibilities, changed[3].responsibilities)
        np.testing.assert_array_equal(original[2], changed[2])
        np.testing.assert_array_equal(original[1][:8], changed[1][:8])
        relative = target.basis@v[8:]
        expected = .5*np.sum(relative**2*(1/sigmas**2-.25))
        np.testing.assert_allclose(changed[0]-original[0], expected, atol=1e-7, rtol=0)
        objective_calls = 3
        if label == 'S01':
            np.testing.assert_array_equal(sigmas, np.full(len(sigmas), 2.))
            for a, b in zip(original[:3], changed[:3], strict=True):
                np.testing.assert_array_equal(a, b)
        else:
            if not np.any(sigmas != 2.):
                raise ValueError('S03 age policy does not change any supported width')
            profile = age.Profiles(replace(ctx, model=target), v, n)
            objective_calls += 1
            # Three deterministic single-coordinate profile checks. These are
            # proposals under the declared bounds, never a seed projection.
            problem = _Problem(target, v, rf_arm='fitted-c')
            checked, excluded = 0, 0
            for index in np.linspace(0, len(sigmas)-1, 3, dtype=int):
                for step in (.05, -.05):
                    tau = profile.tau.copy()
                    tau[index] += step
                    vv = age.profile.timing_vector(target, v, tau)
                    if problem.feasible(vv):
                        break
                else:
                    excluded += 1
                    continue
                actual = target.evaluate_joint(vv, n)[0]
                objective_calls += 1
                np.testing.assert_allclose(profile.score(tau)[index], actual, atol=1e-7, rtol=0)
                checked += 1
            if checked == 0:
                raise ValueError('no feasible declared single-coordinate profile checks')
            metadata.update(profile_checks=checked, infeasible_profile_checks_excluded=excluded)
        receipts.append(dict(source_id=label, metadata=metadata, objectives=objective_calls,
            source_loader_replay_objectives=2, fits=0,
            qualification='exact scalar2 nest; changed likelihood/posterior/common/nuisance '
                          'gradients unchanged; direct weighted-prior/profile closure'))
    verify_authority()
    common.save_json(HERE/'pilot_qualification.json', dict(rows=receipts, fits=0))


def run(family):
    verify_authority()
    qualified = json.loads((HERE/'pilot_qualification.json').read_text())
    if len(qualified['rows']) != 2:
        raise ValueError('both source qualifications required')
    ctx, parent, sigmas, metadata = prepare('S03')
    selected = np.full_like(sigmas, 2.) if family == 'scalar2' else sigmas
    model = age.RelativeTimingModel(ctx.model, selected)
    full = age.RelativeTimingModel(ctx.full_model, selected)
    outputs = []
    for arm in ('fitted-c', 'zero-c'):
        for method in ('continuation', 'profile'):
            v, n = np.array(parent['vector']), np.array(parent['nuisance'])
            if arm == 'zero-c':
                v[6] = 0.
            counter = Counted(model)
            context = replace(ctx, vector=v, nuisance=n, model=counter, full_model=full,
                fixed_c=arm == 'zero-c', deadline=time.monotonic()+120)
            if method == 'profile':
                result = profile_fit.fit(context, profile_factory=age.Profiles,
                                         max_evaluations=1000, max_seconds=120)
            else:
                result = common.refit(context, v, n, max_evaluations=1000,
                                      max_seconds=120, fixed_c=context.fixed_c)
            if result['diagnostics']['evaluations'] != counter.calls or counter.calls > 1000:
                raise ValueError('exact model-objective budget accounting failed')
            audit = common.endpoint_status(replace(context, model=model),
                                           result['vector'], result['nuisance'])
            path = HERE/f'fit_S03_{family}_{arm}_{method}.json'
            if path.exists():
                raise FileExistsError('no overwrite/retry')
            common.save_json(path, dict(result, family=family, source_id='S03', arm=arm,
                method=method, audit=audit, width_metadata=metadata,
                effective_sigmas_s=selected, independent_terminal_audits=1))
            outputs.append(dict(path=str(path), sha256=digest(path)))
            print(family, arm, method, audit, counter.calls, flush=True)
    verify_authority()
    common.save_json(HERE/f'seal_{family}.json', dict(outcomes=outputs))


def evaluate():
    verify_authority()
    seals = {}
    for family in ('scalar2', 'age'):
        path = HERE/f'seal_{family}.json'
        seal = json.loads(path.read_text())
        if any(digest(r['path']) != r['sha256'] for r in seal['outcomes']):
            raise ValueError('all8 outcomes must seal before evaluation')
        seals[family] = digest(path)
    ctx, _, sigmas, _ = prepare('S03')
    rows = []
    for family in ('scalar2', 'age'):
        selected = np.full_like(sigmas, 2.) if family == 'scalar2' else sigmas
        for arm in ('fitted-c', 'zero-c'):
            context = replace(ctx, fixed_c=arm == 'zero-c',
                model=age.RelativeTimingModel(ctx.model, selected),
                full_model=age.RelativeTimingModel(ctx.full_model, selected))
            for method in ('continuation', 'profile'):
                path = HERE/f'fit_S03_{family}_{arm}_{method}.json'
                result = json.loads(path.read_text())
                v, n = np.array(result['vector']), np.array(result['nuisance'])
                _, _, best, assigned, residual = common.point_state(context.full_model, v, n)
                np.savez_compressed(HERE/f'eval_S03_{family}_{arm}_{method}.npz',
                    associated=assigned, residual_hz=residual,
                    satellite_number=ctx.bank.numbers[best], times_s=ctx.observations.times_s)
                reference = ctx.vector, ctx.nuisance
                rows.append(dict(source_id='S03', family=family, arm=arm, method=method,
                    outcome_sha256=digest(path), audit=common.endpoint_status(context, v, n),
                    diagnostics=result['diagnostics'],
                    full=common.measure(context, v, n, original=reference),
                    challenge=common.measure(context, v, n, original=reference,
                        mask=common.challenge_mask(context))))
    common.save_json(HERE/'pilot_evaluation.json', dict(rows=rows, seals=seals,
        scope='S03-only localization pilot, S01exactnest0fit; not an all5/all15 performance method',
        comparison='NLL, support, position; different-prior J is not Bayesian model evidence',
        postseal_objectives_per_result=6, promotion=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('freeze', 'qualify', 'run', 'evaluate'))
    parser.add_argument('--family', choices=('scalar2', 'age'))
    args = parser.parse_args()
    if args.action == 'freeze':
        freeze()
    elif args.action == 'qualify':
        qualify()
    elif args.action == 'run':
        run(args.family)
    else:
        evaluate()
