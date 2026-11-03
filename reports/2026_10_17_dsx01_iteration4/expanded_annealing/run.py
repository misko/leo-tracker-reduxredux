"""Frozen expanded-bank continuation/annealing; no new candidate selection."""

import argparse
import csv
import hashlib
import importlib
import importlib.util
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREVIOUS = ROOT/'reports/2026_10_16_dsx01_iteration2'
FIXED = ROOT/'reports/2026_10_17_dsx01_iteration3/support/annealing'
sys.path.insert(0, str(PREVIOUS))
expansion = importlib.import_module('bank_expansion')
spec = importlib.util.spec_from_file_location('expanded_anneal_ports', FIXED/'run_remaining.py')
ports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ports)
common, width = ports.pilot.common, ports.pilot.annealing
LABELS = ('S01', 'S02', 'S03', 'S04', 'S05')


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_receipt(saved, numbers, selection, selection_sha):
    if saved['selection_receipt_sha256'] != selection_sha:
        raise ValueError('saved expanded state has different candidate selection')
    if saved['bank_additions'] != selection['selected_ids']:
        raise ValueError('saved additions differ from original generic screen')
    np.testing.assert_array_equal(saved['bank_transport']['expanded_numbers'], numbers)
    if len(saved['vector']) != 7+len(numbers):
        raise ValueError('saved complete timing chart has wrong dimension')


def paired_seed(saved, fixed_c):
    v, n = (np.asarray(saved[k], float).copy() for k in ('vector', 'nuisance'))
    if fixed_c:
        v[6] = 0.
    return dict(vector=v, nuisance=n)


def prepare(label):
    original = common.load_context(label)
    selection_path = PREVIOUS/f'candidate_screen_{label}.json'
    selection = json.loads(selection_path.read_text())
    regional, authority = expansion.regional_bank(original, return_receipt=True)
    context, transport = expansion.expandable_context(original, selection['selected_ids'],
                                                       regional=regional)
    np.testing.assert_array_equal(context.observations.window_ids, original.observations.window_ids)
    parents = {}
    for arm in ('fitted-c', 'zero-c'):
        path = PREVIOUS/'expanded-results'/f'{label}-{arm}-profile.json'
        saved = json.loads(path.read_text())
        validate_receipt(saved, context.bank.numbers, selection, digest(selection_path))
        parents[arm] = saved
    return original, context, parents, dict(regional=authority, expansion=transport)


def source_paths(label):
    paths = [Path(__file__), HERE/'test_run.py', HERE/'PROTOCOL.md',
        FIXED/'model.py', FIXED/'test_model.py', FIXED/'run_remaining.py',
        FIXED/'polish.py', FIXED/'run.py', PREVIOUS/'bank_expansion.py',
        PREVIOUS/'endpoint_polish.py', common.HERE/'common.py',
        PREVIOUS/f'candidate_screen_{label}.json']
    paths += [PREVIOUS/'expanded-results'/f'{label}-{arm}-profile.json'
              for arm in ('fitted-c', 'zero-c')]
    return paths


def run(label):
    authority = {str(path): digest(path) for path in source_paths(label)}
    with (HERE/f'launch_{label}.json').open('x') as stream:
        json.dump(dict(source_sha256=authority, all_sources=list(LABELS),
            policy='same original selected eight additions; no screening/reselection',
            seed='saved expanded fitted-c profile; c0 changes only coefficient6',
            unit_caps=dict(extra_objectives=1000, seconds=120),
            schedule=[[1000, 149], [500, 150], [250, 150], [125, 550]],
            source_generation='retained historical source/screen/profile costs; '
                              'not inside extra budget',
            numerical_policy='raw results retained; one remaining-budget '
                             'immediate finish separately'),
            stream, indent=2)
    begun = time.monotonic()
    _, context, parents, reconstruction = prepare(label)
    source_audits = {}
    for arm, parent in parents.items():
        ctx = replace(context, fixed_c=arm == 'zero-c')
        audit = common.endpoint_status(ctx, parent['vector'], parent['nuisance'])
        if (not audit['feasible'] or abs(audit['training_objective']-
                parent['diagnostics']['objective']) > 1e-7):
            raise ValueError('original expanded endpoint target/domain replay failed')
        source_audits[arm] = audit
    seed = paired_seed(parents['fitted-c'], False)
    base = context.model.evaluate_joint(seed['vector'], seed['nuisance'])
    same = width.WidthModel(context.model, 125).evaluate_joint(seed['vector'], seed['nuisance'])
    for a, b in zip(base[:3], same[:3], strict=True):
        np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(base[3].responsibilities, same[3].responsibilities)
    common.save_json(HERE/f'qualification_{label}.json', dict(source_sha256=authority,
        reconstruction=reconstruction, source_audits=source_audits,
        sigma125_nesting='bit exact objective, gradients and posterior',
        objectives=4, source_loader_replay_objectives=2, localization_fits=0,
        preparation_seconds=time.monotonic()-begun))
    outputs = []
    for arm in ('fitted-c', 'zero-c'):
        for method in ('continuation', 'annealing'):
            ctx = replace(context, fixed_c=arm == 'zero-c', deadline=time.monotonic()+120)
            result = ports.execute(ctx, paired_seed(parents['fitted-c'], ctx.fixed_c), parents[arm],
                                   anneal=method == 'annealing')
            path = HERE/f'fit_{label}_{arm}_{method}.json'
            common.save_json(path, dict(result, source_id=label, arm=arm, method=method,
                source_sha256=authority, candidate_numbers=context.bank.numbers,
                policy='expanded fixed bank; final125J; own-arm raw expanded incumbent retained'))
            outputs.append(dict(path=str(path), sha256=digest(path)))
            print(label, arm, method, result['diagnostics'], flush=True)
    if any(digest(path) != expected for path, expected in authority.items()):
        raise ValueError('frozen expanded-annealing authority changed')
    common.save_json(HERE/f'seal_{label}.json', dict(outcomes=outputs, source_sha256=authority))


def overlap(assigned, residual, numbers, original, mask):
    oa, ores, on = original
    retained = mask & assigned & oa
    def rms(x):
        return float(np.sqrt(np.mean(x*x))) if len(x) else None
    return dict(new_associations=int(np.sum(mask & assigned & ~oa)),
        lost_associations=int(np.sum(mask & ~assigned & oa)),
        retained_associations=int(retained.sum()),
        retained_identity_changes=int(np.sum(retained & (numbers != on))),
        intersection_original_rms_hz=rms(ores[retained]),
        intersection_variant_rms_hz=rms(residual[retained]))


def evaluate():
    seals = {}
    for label in LABELS:
        path = HERE/f'seal_{label}.json'
        seal = json.loads(path.read_text())
        if any(digest(row['path']) != row['sha256'] for row in seal['outcomes']):
            raise ValueError('all20 outcomes must seal before evaluation')
        seals[label] = digest(path)
    with (common.DATASET/'membership.csv').open() as stream:
        memberships = list(csv.DictReader(stream))
    rows, finished = [], []
    for label in LABELS:
        original, context, _, _ = prepare(label)
        _, _, ob, oa, ores = common.point_state(original.full_model,
                                               original.vector, original.nuisance)
        reference = oa, ores, original.bank.numbers[ob]
        mask = common.challenge_mask(context)
        region_ids = {r['region_id'] for r in memberships if r['source_id'] == label}
        masks = {region: np.isin(context.observations.window_ids,
            [r['observation_id'] for r in memberships if r['region_id'] == region])
            for region in sorted(region_ids)}
        for arm in ('fitted-c', 'zero-c'):
            ctx = replace(context, fixed_c=arm == 'zero-c')
            for method in ('continuation', 'annealing'):
                path = HERE/f'fit_{label}_{arm}_{method}.json'
                saved = json.loads(path.read_text())
                variants = [('raw', saved['raw'])]
                if saved['supplement']:
                    variants.append(('finished', saved))
                for variant, result in variants:
                    v, n = np.array(result['vector']), np.array(result['nuisance'])
                    audit = common.endpoint_status(ctx, v, n)
                    _, _, best, assigned, residual = common.point_state(ctx.full_model, v, n)
                    numbers = ctx.bank.numbers[best]
                    prefix = 'eval' if variant == 'raw' else 'finished_eval'
                    np.savez_compressed(HERE/f'{prefix}_{label}_{arm}_{method}.npz',
                        associated=assigned, residual_hz=residual, satellite_number=numbers,
                        times_s=ctx.observations.times_s)
                    full = common.measure(ctx, v, n)
                    challenge = common.measure(ctx, v, n, mask=mask)
                    full.update(overlap(assigned, residual, numbers, reference,
                                        np.ones(len(mask), bool)))
                    challenge.update(overlap(assigned, residual, numbers, reference, mask))
                    row = dict(source_id=label, arm=arm, method=method, variant=variant,
                        outcome_sha256=digest(path), diagnostics=result['diagnostics'], audit=audit,
                        full=full, challenge=challenge,
                        windows={name: dict(observations=int(use.sum()),
                            associated=int(assigned[use].sum())) for name, use in masks.items()})
                    (rows if variant == 'raw' else finished).append(row)
                    if variant == 'raw':
                        common.save_json(HERE/f'raw_fit_{label}_{arm}_{method}.json', dict(
                            vector=v, nuisance=n, diagnostics=result['diagnostics'],
                            parent_sha256=digest(path), policy='raw inference endpoint only'))
        print(label, 'postseal raw/finished evaluation complete', flush=True)
    aggregate = []
    for arm in ('fitted-c', 'zero-c'):
        for method in ('continuation', 'annealing'):
            group = [r for r in rows if r['arm'] == arm and r['method'] == method]
            aggregate.append(dict(arm=arm, method=method,
                observations=sum(r['full']['observations'] for r in group),
                associated=sum(r['full']['associated'] for r in group),
                challenge_observations=sum(r['challenge']['observations'] for r in group),
                challenge_associated=sum(r['challenge']['associated'] for r in group),
                strict=sum(r['audit']['accepted'] for r in group),
                inference_objectives=sum(r['diagnostics']['evaluations'] for r in group)))
    common.save_json(HERE/'evaluation.json', dict(rows=rows, aggregate=aggregate, seals=seals,
        reference='same original published fitted-c state, compared by catalogue IDs across banks',
        raw_postseal_objectives_per_result=4, original_reference_objectives_per_case=1,
        context_loader_replay_objectives_per_case=2, promotion=False))
    common.save_json(HERE/'finishing_evaluation.json', dict(rows=finished, promotion=False,
        policy='all numerical finishing remains separate from primary raw series'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('run', 'evaluate'))
    parser.add_argument('--source', choices=LABELS)
    args = parser.parse_args()
    run(args.source) if args.action == 'run' else evaluate()
